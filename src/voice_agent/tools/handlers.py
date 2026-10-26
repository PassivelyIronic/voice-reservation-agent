"""Thin adapters: parse arguments, call the domain, render text, wrap in the result envelope.

Envelope: {"ok": true, "data": {...}} or {"ok": false, "error": {code, agent_hint, retryable},
"data": {...optional details}}.
"""

import random
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from voice_agent.dialogue import renderers
from voice_agent.dialogue.state import ConversationState
from voice_agent.domain import allergens, handoff, info, menu, reservations
from voice_agent.domain.availability import Slot
from voice_agent.domain.clock import RESTAURANT_TZ, Clock
from voice_agent.domain.errors import DomainError, ErrorCode
from voice_agent.domain.ids import IdGenerator

Envelope = dict[str, Any]

AGENT_HINTS: dict[ErrorCode, str] = {
    ErrorCode.INVALID_DATE: "Ask the caller for the date and time again.",
    ErrorCode.IN_THE_PAST: "That time has passed. Ask the caller for another time.",
    ErrorCode.OUT_OF_WINDOW: "Bookings are possible up to 30 days ahead. Ask for an earlier date.",
    ErrorCode.TOO_SOON: "Bookings need at least 60 minutes notice. Offer a later time.",
    ErrorCode.CLOSED: "We are closed then. Tell the caller and offer data.next_open.",
    ErrorCode.LARGE_PARTY: (
        "Parties above 8 are handled by staff. Call transfer_to_human with reason large_party."
    ),
    ErrorCode.SLOT_GRID: "Bookings start every 15 minutes. Offer data.suggested_time.",
    ErrorCode.NO_AVAILABILITY: "Offer the alternatives.",
    ErrorCode.HOLD_NOT_FOUND: "There is no active hold. Call check_availability again.",
    ErrorCode.HOLD_EXPIRED: (
        "The hold expired. Tell the caller and call check_availability again."
    ),
    ErrorCode.HOLD_FOREIGN: "That hold is not from this call. Call check_availability again.",
    ErrorCode.CONFIRMATION_REQUIRED: (
        "Read the readback to the caller and wait for an explicit yes in their next message."
    ),
    ErrorCode.INVALID_PHONE: "Ask the caller to repeat the phone number.",
    ErrorCode.SLOT_TAKEN: "The slot was just taken. Offer the alternatives.",
    ErrorCode.ITEM_NOT_FOUND: "Call search_menu first and use an item_id from its result.",
    ErrorCode.TOOL_ERROR: (
        "Retry once. If it fails again, apologise and call transfer_to_human "
        "with reason tool_failure."
    ),
}


@dataclass
class ToolContext:
    """Everything a handler needs; passed to Pipecat as app_resources."""

    conn: sqlite3.Connection
    clock: Clock
    ids: IdGenerator
    state: ConversationState
    tool_timeout_secs: float = 2.0
    faults: dict[str, tuple[str, float]] = field(default_factory=dict[str, tuple[str, float]])
    fault_rng: random.Random = field(default_factory=lambda: random.Random(0))


def ok(data: dict[str, Any]) -> Envelope:
    return {"ok": True, "data": data}


def error(code: ErrorCode, data: dict[str, Any] | None = None) -> Envelope:
    envelope: Envelope = {
        "ok": False,
        "error": {
            "code": code.value,
            "agent_hint": AGENT_HINTS[code],
            "retryable": code is ErrorCode.TOOL_ERROR,
        },
    }
    if data:
        envelope["data"] = data
    return envelope


def error_details(exc: DomainError) -> dict[str, Any]:
    details: dict[str, Any] = {}
    if "suggested_time" in exc.details:
        details["suggested_time"] = exc.details["suggested_time"]
    next_open = exc.details.get("next_open")
    if isinstance(next_open, dict):
        details["next_open"] = {
            **next_open,
            "readback": renderers.next_open_readback(next_open),  # type: ignore[arg-type]
        }
    if exc.details.get("closure_reason"):
        details["closure_reason"] = exc.details["closure_reason"]
    return details


def _slot_dict(slot: Slot) -> dict[str, str]:
    return {
        "date": slot.date.isoformat(),
        "time": slot.time.strftime("%H:%M"),
        "readback": renderers.slot_readback(slot),
    }


# --- handlers ---


def get_restaurant_info(ctx: ToolContext, args: dict[str, Any]) -> Envelope:
    topic = str(args["topic"])
    if topic == "opening_hours":
        raw_date = args.get("date")
        try:
            day = (
                date.fromisoformat(raw_date)
                if raw_date
                else ctx.clock.now().astimezone(RESTAURANT_TZ).date()
            )
        except ValueError:
            return error(ErrorCode.INVALID_DATE)
        answer = renderers.opening_hours_answer(info.hours_on(ctx.conn, day))
    else:
        found = info.info_answer(ctx.conn, topic)
        if found is None:
            return error(ErrorCode.TOOL_ERROR)
        answer = found
    return ok({"topic": topic, "spoken_answer": answer})


def check_availability(ctx: ToolContext, args: dict[str, Any]) -> Envelope:
    result = reservations.check_availability(
        ctx.conn,
        ctx.clock,
        ctx.ids,
        ctx.state.conversation_id,
        str(args["date"]),
        str(args["time"]),
        int(args["party_size"]),
        str(args.get("zone_preference") or "any"),
    )
    if ctx.state.hold_id:
        ctx.state.clear_hold()  # the domain released it
    if not result.available:
        return ok(
            {"available": False, "alternatives": [_slot_dict(a) for a in result.alternatives]}
        )
    assert result.hold_id and result.expires_at and result.table_zone
    ctx.state.record_hold(result.hold_id, result.slot, result.party_size, result.expires_at)
    return ok(
        {
            "available": True,
            "hold_id": result.hold_id,
            "hold_expires_in_s": int((result.expires_at - ctx.clock.now()).total_seconds()),
            "date": result.slot.date.isoformat(),
            "time": result.slot.time.strftime("%H:%M"),
            "party_size": result.party_size,
            "table_zone": result.table_zone,
            "readback": renderers.hold_readback(result.slot, result.party_size),
        }
    )


def create_reservation(ctx: ToolContext, args: dict[str, Any]) -> Envelope:
    hold_id = str(args["hold_id"])
    if ctx.state.hold_turns.get(hold_id) == ctx.state.turn:
        hold_slot = ctx.state.slot if ctx.state.hold_id == hold_id else None
        data = (
            {"readback": renderers.hold_readback(hold_slot, ctx.state.party_size or 0)}
            if hold_slot and ctx.state.party_size
            else None
        )
        return error(ErrorCode.CONFIRMATION_REQUIRED, data)
    confirmation = reservations.create_reservation(
        ctx.conn,
        ctx.clock,
        ctx.ids,
        ctx.state.conversation_id,
        hold_id,
        str(args["customer_name"]),
        str(args["phone"]),
        args.get("notes") or None,
        source="text",
    )
    ctx.state.clear_hold()
    ctx.state.customer_name = confirmation.customer_name
    ctx.state.confirmation_code = confirmation.code
    return ok(
        {
            "code": confirmation.code,
            "readback": renderers.confirmation_readback(
                confirmation.slot,
                confirmation.party_size,
                confirmation.customer_name,
                confirmation.code,
            ),
        }
    )


def search_menu(ctx: ToolContext, args: dict[str, Any]) -> Envelope:
    result = menu.search_menu(ctx.conn, str(args["query"]), str(args.get("category") or "any"))
    return ok(
        {
            "match": result.match,
            "candidates": [
                {
                    "item_id": c.item_id,
                    "name": c.name,
                    "category": c.category,
                    "sold_out": c.sold_out,
                }
                for c in result.candidates
            ],
        }
    )


def get_allergen_info(ctx: ToolContext, args: dict[str, Any]) -> Envelope:
    asked = [str(a) for a in args["allergens"]]
    lookup = allergens.lookup_allergens(ctx.conn, str(args["item_id"]), asked)
    spoken, offer = renderers.allergen_answer(lookup)
    token = ctx.state.approve_allergen_answer(renderers.split_sentences(spoken))
    return ok(
        {
            "item_id": lookup.item_id,
            "item_name": lookup.item_name,
            "results": [
                {
                    "asked": r.asked,
                    "code": r.code,
                    "status": r.status,
                    "related_ingredients": [
                        {"name": i.name, "note": i.note} for i in r.related_ingredients
                    ],
                }
                for r in lookup.results
            ],
            "spoken_answer": spoken,
            "requires_handoff_offer": offer,
            "guard_token": token,
        }
    )


def transfer_to_human(ctx: ToolContext, args: dict[str, Any]) -> Envelope:
    ticket_id = handoff.create_ticket(
        ctx.conn,
        ctx.clock,
        ctx.state.conversation_id,
        args["reason"],
        str(args["summary"]),
    )
    ctx.state.ended = True
    return ok({"ticket_id": ticket_id, "spoken_answer": renderers.HANDOFF_ANNOUNCEMENT})


HANDLERS: dict[str, Callable[[ToolContext, dict[str, Any]], Envelope]] = {
    "get_restaurant_info": get_restaurant_info,
    "check_availability": check_availability,
    "create_reservation": create_reservation,
    "search_menu": search_menu,
    "get_allergen_info": get_allergen_info,
    "transfer_to_human": transfer_to_human,
}
