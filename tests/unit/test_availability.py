"""Business rules from the table in docs/plan/04-data-model.md. Frozen now: Mon 2026-10-26 13:00."""

import sqlite3
from datetime import date, datetime, time

import pytest

from voice_agent.domain.availability import Slot, slot_keys
from voice_agent.domain.clock import RESTAURANT_TZ, FrozenClock
from voice_agent.domain.errors import DomainError, ErrorCode
from voice_agent.domain.ids import IdGenerator
from voice_agent.domain.reservations import AvailabilityResult, check_availability

_conversations = iter(range(10_000))


def check(
    db: sqlite3.Connection,
    clock: FrozenClock,
    ids: IdGenerator,
    day: str,
    at: str,
    party: int,
    zone: str = "any",
) -> AvailabilityResult:
    return check_availability(db, clock, ids, f"conv-{next(_conversations)}", day, at, party, zone)


def error_of(
    db: sqlite3.Connection, clock: FrozenClock, ids: IdGenerator, *args: object
) -> DomainError:
    with pytest.raises(DomainError) as exc:
        check(db, clock, ids, *args)  # type: ignore[arg-type]
    return exc.value


def fill(
    db: sqlite3.Connection, clock: FrozenClock, ids: IdGenerator, day: str, at: str, party: int
) -> None:
    """Hold every table that fits `party` at the given slot."""
    while check(db, clock, ids, day, at, party).available:
        pass


# --- booking window, lead time, past ---


def test_last_day_of_window_is_bookable(db, clock, ids) -> None:
    assert check(db, clock, ids, "2026-11-25", "19:00", 2).available  # today + 30, Wednesday


def test_beyond_window_is_rejected(db, clock, ids) -> None:
    assert error_of(db, clock, ids, "2026-11-26", "19:00", 2).code == ErrorCode.OUT_OF_WINDOW


def test_past_date_is_rejected(db, clock, ids) -> None:
    assert error_of(db, clock, ids, "2026-10-24", "19:00", 2).code == ErrorCode.IN_THE_PAST


def test_less_than_60_minutes_ahead_is_too_soon(db, ids) -> None:
    tuesday_evening = FrozenClock(datetime(2026, 10, 27, 18, 30, tzinfo=RESTAURANT_TZ))
    assert error_of(db, tuesday_evening, ids, "2026-10-27", "19:15", 2).code == ErrorCode.TOO_SOON
    assert check(db, tuesday_evening, ids, "2026-10-27", "19:30", 2).available


def test_unparseable_date_is_invalid(db, clock, ids) -> None:
    assert error_of(db, clock, ids, "2026-13-40", "19:00", 2).code == ErrorCode.INVALID_DATE


# --- grid ---


def test_off_grid_time_suggests_nearest_slot(db, clock, ids) -> None:
    err = error_of(db, clock, ids, "2026-10-27", "19:10", 2)
    assert err.code == ErrorCode.SLOT_GRID
    assert err.details["suggested_time"] == "19:15"


def test_reservation_covers_eight_quarter_hour_slots() -> None:
    keys = slot_keys(Slot(date(2026, 10, 27), time(19, 30)))
    assert keys[0] == "2026-10-27T19:30"
    assert keys[-1] == "2026-10-27T21:15"
    assert len(keys) == 8


# --- opening hours ---


def test_monday_is_closed_with_next_open(db, clock, ids) -> None:
    err = error_of(db, clock, ids, "2026-11-02", "19:00", 2)
    assert err.code == ErrorCode.CLOSED
    assert err.details["next_open"] == {
        "date": "2026-11-03",
        "open_time": "12:00",
        "last_seating": "21:00",
    }


def test_after_last_seating_is_closed(db, clock, ids) -> None:
    err = error_of(db, clock, ids, "2026-10-27", "21:15", 2)
    assert err.code == ErrorCode.CLOSED
    assert err.details["next_open"]["date"] == "2026-10-28"  # type: ignore[index]
    assert check(db, clock, ids, "2026-10-27", "21:00", 2).available


def test_before_opening_points_to_same_day(db, clock, ids) -> None:
    err = error_of(db, clock, ids, "2026-10-27", "11:30", 2)
    assert err.code == ErrorCode.CLOSED
    assert err.details["next_open"]["date"] == "2026-10-27"  # type: ignore[index]


def test_friday_has_later_last_seating(db, clock, ids) -> None:
    assert check(db, clock, ids, "2026-10-30", "21:30", 2).available


def test_special_closure(db, clock, ids) -> None:
    err = error_of(db, clock, ids, "2026-11-11", "19:00", 2)
    assert err.code == ErrorCode.CLOSED
    assert err.details["closure_reason"]
    assert err.details["next_open"]["date"] == "2026-11-12"  # type: ignore[index]


# --- party size and table assignment ---


def test_party_above_eight_is_large_party(db, clock, ids) -> None:
    assert error_of(db, clock, ids, "2026-10-27", "19:00", 9).code == ErrorCode.LARGE_PARTY


@pytest.mark.parametrize(
    ("party", "capacity"), [(1, 2), (2, 2), (3, 4), (4, 4), (5, 6), (6, 6), (7, 8), (8, 8)]
)
def test_best_fit_picks_smallest_table(db, clock, ids, party: int, capacity: int) -> None:
    result = check(db, clock, ids, "2026-10-27", "19:00", party)
    table_capacity = db.execute(
        "SELECT capacity FROM dining_tables t JOIN holds h ON h.table_id = t.id WHERE h.id = ?",
        (result.hold_id,),
    ).fetchone()[0]
    assert table_capacity == capacity


def test_best_fit_moves_up_when_small_tables_are_taken(db, clock, ids) -> None:
    check(db, clock, ids, "2026-10-27", "19:00", 2)
    check(db, clock, ids, "2026-10-27", "19:00", 2)  # both 2-tops now held
    result = check(db, clock, ids, "2026-10-27", "19:00", 2)
    assert result.available
    assert result.table_zone == "window"  # T3, the first 4-top


def test_zone_preference_filters_tables(db, clock, ids) -> None:
    result = check(db, clock, ids, "2026-10-27", "19:00", 4, "terrace")
    assert result.table_zone == "terrace"


# --- alternatives ---


def test_alternatives_are_nearest_slots_within_90_minutes(db, clock, ids) -> None:
    fill(db, clock, ids, "2026-10-27", "20:00", 4)  # blocks 4+ starts from 18:15 to 21:45
    result = check(db, clock, ids, "2026-10-27", "19:00", 4)
    assert not result.available
    assert [a.time for a in result.alternatives] == [time(18, 0), time(17, 45), time(17, 30)]


def test_alternatives_fall_back_to_same_time_next_day(seeded_db, clock, ids) -> None:
    # Seeded first Friday after the reference date is fully booked for 4+ in the evening.
    result = check(seeded_db, clock, ids, "2026-10-30", "19:30", 4)
    assert not result.available
    assert result.alternatives == (Slot(date(2026, 10, 31), time(19, 30)),)
