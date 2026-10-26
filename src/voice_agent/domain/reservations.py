"""Holds (check_availability) and their conversion into reservations (create_reservation)."""

import re
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from voice_agent.db import repository as repo
from voice_agent.db.connection import immediate
from voice_agent.domain.availability import (
    Slot,
    find_alternatives,
    find_table,
    parse_slot,
    slot_keys,
    validate_request,
)
from voice_agent.domain.clock import Clock
from voice_agent.domain.errors import DomainError, ErrorCode
from voice_agent.domain.ids import IdGenerator
from voice_agent.domain.policy import HOLD_TTL, RESERVATION_DURATION


@dataclass(frozen=True)
class AvailabilityResult:
    available: bool
    slot: Slot
    party_size: int
    hold_id: str | None = None
    expires_at: datetime | None = None
    table_zone: str | None = None
    alternatives: tuple[Slot, ...] = ()


@dataclass(frozen=True)
class Confirmation:
    code: str
    slot: Slot
    party_size: int
    customer_name: str
    table_zone: str


def normalize_phone(raw: str) -> str:
    """Keep a leading '+' and digits; 7-15 digits (E.164 maximum)."""
    digits = re.sub(r"\D", "", raw)
    if not 7 <= len(digits) <= 15:
        raise DomainError(ErrorCode.INVALID_PHONE, "Phone number must have 7 to 15 digits.")
    return ("+" if raw.strip().startswith("+") else "") + digits


def _expires_at(hold: repo.Hold) -> datetime:
    return datetime.fromisoformat(hold.expires_at)


def _expire_stale_holds(conn: sqlite3.Connection, now: datetime) -> None:
    for hold in repo.get_active_holds(conn):
        if _expires_at(hold) <= now:
            repo.close_hold(conn, hold.id, "EXPIRED")


def check_availability(
    conn: sqlite3.Connection,
    clock: Clock,
    ids: IdGenerator,
    conversation_id: str,
    date: str,
    time: str,
    party_size: int,
    zone_preference: str = "any",
) -> AvailabilityResult:
    """Validate the request and place a hold on the best-fit table, or return alternatives.

    A new check in the same conversation releases that conversation's previous hold
    (the customer changed their mind), whether or not the new slot is available.
    """
    now = clock.now()
    slot = parse_slot(date, time)
    validate_request(conn, now, slot, party_size)
    try:
        with immediate(conn):
            _expire_stale_holds(conn, now)
            for hold in repo.get_active_holds(conn):
                if hold.conversation_id == conversation_id:
                    repo.close_hold(conn, hold.id, "RELEASED")
            table = find_table(conn, slot, party_size, zone_preference)
            if table is not None:
                hold_id = ids.hold_id()
                while repo.get_hold(conn, hold_id) is not None:
                    hold_id = ids.hold_id()
                expires_at = now + HOLD_TTL
                repo.insert_hold(
                    conn,
                    repo.Hold(
                        id=hold_id,
                        table_id=table.id,
                        date=slot.date,
                        start_time=slot.time,
                        party_size=party_size,
                        conversation_id=conversation_id,
                        expires_at=expires_at.astimezone(UTC).isoformat(),
                        status="ACTIVE",
                    ),
                )
                repo.insert_slots(conn, table.id, slot_keys(slot), hold_id=hold_id)
                return AvailabilityResult(
                    available=True,
                    slot=slot,
                    party_size=party_size,
                    hold_id=hold_id,
                    expires_at=expires_at,
                    table_zone=table.zone,
                )
    except sqlite3.IntegrityError:
        pass  # Lost a race for the slot: fall through to alternatives.
    alternatives = find_alternatives(conn, now, slot, party_size, zone_preference)
    return AvailabilityResult(
        available=False, slot=slot, party_size=party_size, alternatives=tuple(alternatives)
    )


def create_reservation(
    conn: sqlite3.Connection,
    clock: Clock,
    ids: IdGenerator,
    conversation_id: str,
    hold_id: str,
    customer_name: str,
    phone: str,
    notes: str | None = None,
    source: str = "text",
) -> Confirmation:
    """Convert an active hold of this conversation into a confirmed reservation.

    CONFIRMATION_REQUIRED (hold created in the same user turn) is enforced by the tool layer,
    which owns the notion of turns.
    """
    now = clock.now()
    normalized_phone = normalize_phone(phone)
    confirmation: Confirmation | None = None
    with immediate(conn):
        hold = repo.get_hold(conn, hold_id)
        if hold is None or hold.status in ("RELEASED", "CONVERTED"):
            raise DomainError(ErrorCode.HOLD_NOT_FOUND, f"No active hold {hold_id}.")
        if hold.conversation_id != conversation_id:
            raise DomainError(ErrorCode.HOLD_FOREIGN, "The hold belongs to another conversation.")
        if hold.status == "EXPIRED" or _expires_at(hold) <= now:
            # Commit the expiry (frees the slots) before reporting it.
            repo.close_hold(conn, hold.id, "EXPIRED")
        else:
            code = ids.reservation_code()
            while repo.reservation_code_exists(conn, code):
                code = ids.reservation_code()
            slot = Slot(hold.date, hold.start_time)
            reservation_id = repo.insert_reservation(
                conn,
                repo.NewReservation(
                    code=code,
                    customer_name=customer_name.strip(),
                    phone=normalized_phone,
                    party_size=hold.party_size,
                    date=hold.date,
                    start_time=hold.start_time,
                    duration_min=RESERVATION_DURATION // timedelta(minutes=1),
                    table_id=hold.table_id,
                    notes=notes,
                    source=source,
                    created_at=now.isoformat(),
                ),
            )
            repo.close_hold(conn, hold.id, "CONVERTED")
            repo.insert_slots(conn, hold.table_id, slot_keys(slot), reservation_id=reservation_id)
            zone = next(t.zone for t in repo.get_tables(conn) if t.id == hold.table_id)
            confirmation = Confirmation(
                code=code,
                slot=slot,
                party_size=hold.party_size,
                customer_name=customer_name.strip(),
                table_zone=zone,
            )
    if confirmation is None:
        raise DomainError(ErrorCode.HOLD_EXPIRED, "The hold expired. Check availability again.")
    return confirmation
