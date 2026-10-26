import re
import sqlite3
from datetime import timedelta

import pytest

from voice_agent.domain.errors import DomainError, ErrorCode
from voice_agent.domain.policy import HOLD_TTL
from voice_agent.domain.reservations import (
    check_availability,
    create_reservation,
    normalize_phone,
)

DAY, AT = "2026-10-27", "19:30"


def hold(db, clock, ids, conversation: str = "conv-a", at: str = AT, party: int = 4) -> str:
    result = check_availability(db, clock, ids, conversation, DAY, at, party)
    assert result.available and result.hold_id
    return result.hold_id


def book(db, clock, ids, hold_id: str, conversation: str = "conv-a"):
    return create_reservation(
        db, clock, ids, conversation, hold_id, "Anna", "555 0101", "nut allergy"
    )


def status_of(db: sqlite3.Connection, hold_id: str) -> str:
    return db.execute("SELECT status FROM holds WHERE id = ?", (hold_id,)).fetchone()[0]


def slot_count(db: sqlite3.Connection, column: str, value: object) -> int:
    return db.execute(
        f"SELECT COUNT(*) FROM reservation_slots WHERE {column} = ?", (value,)
    ).fetchone()[0]


def test_hold_places_slots_and_ttl(db, clock, ids) -> None:
    result = check_availability(db, clock, ids, "conv-a", DAY, AT, 4)
    assert result.available
    assert result.expires_at == clock.now() + HOLD_TTL
    assert slot_count(db, "hold_id", result.hold_id) == 8


def test_confirming_a_hold_creates_reservation(db, clock, ids) -> None:
    hold_id = hold(db, clock, ids)
    confirmation = book(db, clock, ids, hold_id)
    assert re.fullmatch(r"OV-[2-9A-HJ-NP-Z]{4}", confirmation.code)
    row = db.execute("SELECT * FROM reservations WHERE code = ?", (confirmation.code,)).fetchone()
    assert (row["date"], row["start_time"], row["party_size"]) == (DAY, AT, 4)
    assert (row["status"], row["phone"], row["notes"]) == ("CONFIRMED", "5550101", "nut allergy")
    assert row["duration_min"] == 120
    assert status_of(db, hold_id) == "CONVERTED"
    assert slot_count(db, "hold_id", hold_id) == 0
    assert slot_count(db, "reservation_id", row["id"]) == 8


def test_reservation_code_alphabet_excludes_ambiguous_characters(ids) -> None:
    codes = {ids.reservation_code() for _ in range(500)}
    assert not any(set(code[3:]) & set("0O1I") for code in codes)


def test_hold_is_valid_just_before_ttl(db, clock, ids) -> None:
    hold_id = hold(db, clock, ids)
    clock.advance(HOLD_TTL - timedelta(seconds=1))
    assert book(db, clock, ids, hold_id).code


def test_expired_hold_is_rejected_and_slots_freed(db, clock, ids) -> None:
    hold_id = hold(db, clock, ids)
    clock.advance(HOLD_TTL)
    with pytest.raises(DomainError) as exc:
        book(db, clock, ids, hold_id)
    assert exc.value.code == ErrorCode.HOLD_EXPIRED
    assert status_of(db, hold_id) == "EXPIRED"
    assert slot_count(db, "hold_id", hold_id) == 0


def test_expired_holds_do_not_block_other_callers(db, clock, ids) -> None:
    for conversation in ("a", "b", "c", "d", "e", "f", "g", "h", "i", "j"):
        hold(db, clock, ids, conversation)  # every table for 4+ is now held
    assert not check_availability(db, clock, ids, "late", DAY, AT, 4).available
    clock.advance(HOLD_TTL)
    assert check_availability(db, clock, ids, "late", DAY, AT, 4).available


def test_new_hold_in_same_conversation_releases_previous(db, clock, ids) -> None:
    first = hold(db, clock, ids)
    second = hold(db, clock, ids, at="20:00", party=6)
    assert status_of(db, first) == "RELEASED"
    assert slot_count(db, "hold_id", first) == 0
    assert status_of(db, second) == "ACTIVE"
    with pytest.raises(DomainError) as exc:
        book(db, clock, ids, first)
    assert exc.value.code == ErrorCode.HOLD_NOT_FOUND


def test_hold_from_another_conversation_is_foreign(db, clock, ids) -> None:
    hold_id = hold(db, clock, ids, "conv-a")
    with pytest.raises(DomainError) as exc:
        book(db, clock, ids, hold_id, conversation="conv-b")
    assert exc.value.code == ErrorCode.HOLD_FOREIGN


def test_unknown_hold(db, clock, ids) -> None:
    with pytest.raises(DomainError) as exc:
        book(db, clock, ids, "H-0000")
    assert exc.value.code == ErrorCode.HOLD_NOT_FOUND


def test_hold_cannot_be_confirmed_twice(db, clock, ids) -> None:
    hold_id = hold(db, clock, ids)
    book(db, clock, ids, hold_id)
    with pytest.raises(DomainError) as exc:
        book(db, clock, ids, hold_id)
    assert exc.value.code == ErrorCode.HOLD_NOT_FOUND


@pytest.mark.parametrize(
    ("raw", "normalized"),
    [("555 0101", "5550101"), ("+48 600-100-200", "+48600100200"), ("(12) 345 67 89", "123456789")],
)
def test_phone_is_normalized(raw: str, normalized: str) -> None:
    assert normalize_phone(raw) == normalized


@pytest.mark.parametrize("raw", ["12", "", "call me", "1234567890123456"])
def test_invalid_phone(raw: str) -> None:
    with pytest.raises(DomainError) as exc:
        normalize_phone(raw)
    assert exc.value.code == ErrorCode.INVALID_PHONE
