import asyncio
import random
import sqlite3

import pytest

from voice_agent.dialogue.state import ConversationState
from voice_agent.domain.clock import FrozenClock
from voice_agent.domain.ids import IdGenerator
from voice_agent.tools import handlers
from voice_agent.tools.handlers import ToolContext
from voice_agent.tools.registry import parse_faults, run_tool
from voice_agent.tools.schemas import TOOL_SPECS


@pytest.fixture
def ctx(db: sqlite3.Connection, clock: FrozenClock, ids: IdGenerator) -> ToolContext:
    state = ConversationState(conversation_id="conv-test")
    state.start_turn()
    return ToolContext(conn=db, clock=clock, ids=ids, state=state, tool_timeout_secs=0.2)


def call(ctx: ToolContext, name: str, **args: object) -> dict:
    return asyncio.run(run_tool(ctx, name, args))


def test_schemas_cover_six_tools_from_spec() -> None:
    assert [s.name for s in TOOL_SPECS] == [
        "get_restaurant_info",
        "check_availability",
        "create_reservation",
        "search_menu",
        "get_allergen_info",
        "transfer_to_human",
    ]
    assert set(handlers.HANDLERS) == {s.name for s in TOOL_SPECS}


def test_hold_then_confirm_in_a_later_turn(ctx: ToolContext) -> None:
    held = call(ctx, "check_availability", date="2026-10-27", time="19:30", party_size=4)
    assert held["ok"] and held["data"]["available"]
    assert held["data"]["readback"] == "a table for 4 on Tuesday, October 27th at 7:30 PM"
    assert held["data"]["hold_expires_in_s"] == 300
    hold_id = held["data"]["hold_id"]

    same_turn = call(
        ctx, "create_reservation", hold_id=hold_id, customer_name="Anna", phone="5550101"
    )
    assert same_turn["ok"] is False
    assert same_turn["error"]["code"] == "CONFIRMATION_REQUIRED"
    assert same_turn["error"]["retryable"] is False

    ctx.state.start_turn()
    booked = call(
        ctx,
        "create_reservation",
        hold_id=hold_id,
        customer_name="Anna",
        phone="555 0101",
        notes="nut allergy",
    )
    assert booked["ok"], booked
    assert booked["data"]["readback"].startswith("You're booked: a table for 4 on Tuesday")
    assert ctx.state.confirmation_code == booked["data"]["code"]
    assert ctx.state.hold_id is None


def test_domain_errors_become_envelopes(ctx: ToolContext) -> None:
    result = call(ctx, "check_availability", date="2026-10-27", time="19:30", party_size=12)
    assert result == {
        "ok": False,
        "error": {
            "code": "LARGE_PARTY",
            "agent_hint": handlers.AGENT_HINTS[handlers.ErrorCode.LARGE_PARTY],
            "retryable": False,
        },
    }
    assert "transfer_to_human" in result["error"]["agent_hint"]


def test_closed_includes_next_open_readback(ctx: ToolContext) -> None:
    result = call(ctx, "check_availability", date="2026-11-02", time="19:00", party_size=2)
    assert result["error"]["code"] == "CLOSED"
    assert result["data"]["next_open"]["readback"] == (
        "Tuesday, November 3rd, from noon, with the last seating at 9 PM"
    )


def test_slot_grid_suggests_time(ctx: ToolContext) -> None:
    result = call(ctx, "check_availability", date="2026-10-27", time="19:10", party_size=2)
    assert result["error"]["code"] == "SLOT_GRID"
    assert result["data"]["suggested_time"] == "19:15"


def test_unavailable_returns_alternatives_with_readbacks(seeded_db, clock, ids) -> None:
    ctx = ToolContext(conn=seeded_db, clock=clock, ids=ids, state=ConversationState("c"))
    result = call(ctx, "check_availability", date="2026-10-30", time="19:30", party_size=4)
    assert result["data"] == {
        "available": False,
        "alternatives": [
            {"date": "2026-10-31", "time": "19:30", "readback": "Saturday, October 31st at 7:30 PM"}
        ],
    }


def test_restaurant_info(ctx: ToolContext) -> None:
    hours = call(ctx, "get_restaurant_info", topic="opening_hours", date="2026-10-30")
    assert hours["data"]["spoken_answer"] == (
        "On Friday, October 30th we're open from noon to 11 PM; the last seating is at 9:30 PM."
    )
    closed = call(ctx, "get_restaurant_info", topic="opening_hours", date="2026-11-11")
    assert "we're closed" in closed["data"]["spoken_answer"]
    parking = call(ctx, "get_restaurant_info", topic="parking")
    assert parking["ok"] and parking["data"]["spoken_answer"]


def test_menu_then_allergen_records_guard_approval(ctx: ToolContext) -> None:
    menu = call(ctx, "search_menu", query="pesto")
    assert menu["data"]["match"] == "ambiguous"
    info = call(ctx, "get_allergen_info", item_id="pasta-pesto-genovese", allergens=["nuts"])
    assert info["ok"]
    assert info["data"]["results"][0]["status"] == "FREE"
    assert info["data"]["requires_handoff_offer"] is True
    assert info["data"]["guard_token"] == "AG-1-1"
    assert ctx.state.approved_sentences()[0].startswith(
        "According to our verified allergen records"
    )


def test_unknown_item(ctx: ToolContext) -> None:
    result = call(ctx, "get_allergen_info", item_id="pizza", allergens=["nuts"])
    assert result["error"]["code"] == "ITEM_NOT_FOUND"


def test_transfer_creates_ticket_and_ends(ctx: ToolContext) -> None:
    result = call(ctx, "transfer_to_human", reason="large_party", summary="Party of 12 on Friday.")
    assert result["ok"]
    row = ctx.conn.execute("SELECT reason, conversation_id FROM handoff_tickets").fetchone()
    assert tuple(row) == ("large_party", "conv-test")
    assert ctx.state.ended


def test_injected_error_is_retryable_tool_error(ctx: ToolContext) -> None:
    ctx.faults = parse_faults("search_menu:error:1.0")
    result = call(ctx, "search_menu", query="pesto")
    assert result["error"]["code"] == "TOOL_ERROR"
    assert result["error"]["retryable"] is True


def test_injected_timeout_hits_tool_timeout(ctx: ToolContext) -> None:
    ctx.faults = parse_faults("search_menu:timeout:1.0")
    assert call(ctx, "search_menu", query="pesto")["error"]["code"] == "TOOL_ERROR"


def test_fault_probability_is_seeded(ctx: ToolContext) -> None:
    def outcomes() -> list[bool]:
        ctx.fault_rng = random.Random(0)
        ctx.faults = parse_faults("search_menu:error:0.5")
        return [call(ctx, "search_menu", query="pesto")["ok"] for _ in range(8)]

    first = outcomes()
    assert first == outcomes()
    assert True in first and False in first


def test_invalid_fault_spec() -> None:
    with pytest.raises(ValueError):
        parse_faults("search_menu:explode:1.0")
