"""Request validation, best-fit table choice and alternative slots."""

import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from voice_agent.db import repository as repo
from voice_agent.domain.clock import RESTAURANT_TZ
from voice_agent.domain.errors import DomainError, ErrorCode
from voice_agent.domain.policy import (
    ALTERNATIVES_SPAN,
    BOOKING_WINDOW_DAYS,
    MAX_ALTERNATIVES,
    MAX_PARTY_SIZE,
    MIN_LEAD_TIME,
    MIN_PARTY_SIZE,
    RESERVATION_DURATION,
    SLOT_GRID,
)

ZONES = ("any", "main", "window", "terrace")


@dataclass(frozen=True)
class Slot:
    date: date
    time: time

    @property
    def start(self) -> datetime:
        return datetime.combine(self.date, self.time, tzinfo=RESTAURANT_TZ)


def parse_slot(date_str: str, time_str: str) -> Slot:
    try:
        return Slot(date.fromisoformat(date_str), time.fromisoformat(time_str))
    except ValueError as exc:
        raise DomainError(
            ErrorCode.INVALID_DATE, f"Cannot parse date/time: {date_str} {time_str}"
        ) from exc


def slot_keys(slot: Slot) -> list[str]:
    """15-minute grid keys ('YYYY-MM-DDTHH:MM', local time) covered by a reservation at `slot`."""
    start = datetime.combine(slot.date, slot.time)
    count = RESERVATION_DURATION // SLOT_GRID
    return [f"{start + i * SLOT_GRID:%Y-%m-%dT%H:%M}" for i in range(count)]


_GRID_MINUTES = SLOT_GRID // timedelta(minutes=1)


def _round_to_grid(t: time) -> time:
    step = _GRID_MINUTES
    minutes = t.hour * 60 + t.minute + t.second / 60
    rounded = min(int(round(minutes / step) * step), 24 * 60 - step)
    return time(rounded // 60, rounded % 60)


def next_open(conn: sqlite3.Connection, slot: Slot, today: date) -> dict[str, str] | None:
    """First opening within the booking window (same day if requested before opening)."""
    last_day = today + timedelta(days=BOOKING_WINDOW_DAYS)
    day = max(slot.date, today)
    while day <= last_day:
        hours = repo.get_opening_hours(conn, day.weekday())
        if (
            hours
            and hours.open_time
            and hours.last_seating
            and repo.get_closure_reason(conn, day) is None
        ) and (day > slot.date or slot.time < hours.open_time):
            return {
                "date": day.isoformat(),
                "open_time": hours.open_time.strftime("%H:%M"),
                "last_seating": hours.last_seating.strftime("%H:%M"),
            }
        day += timedelta(days=1)
    return None


def validate_request(conn: sqlite3.Connection, now: datetime, slot: Slot, party_size: int) -> None:
    """Raise DomainError for the first violated rule; return None if the slot may be booked."""
    if party_size < MIN_PARTY_SIZE:
        raise ValueError(f"party_size must be >= {MIN_PARTY_SIZE}")
    if party_size > MAX_PARTY_SIZE:
        raise DomainError(
            ErrorCode.LARGE_PARTY, f"Parties above {MAX_PARTY_SIZE} are handled by staff."
        )
    today = now.astimezone(RESTAURANT_TZ).date()
    if slot.start <= now:
        raise DomainError(ErrorCode.IN_THE_PAST, "The requested time is in the past.")
    if slot.date > today + timedelta(days=BOOKING_WINDOW_DAYS):
        raise DomainError(
            ErrorCode.OUT_OF_WINDOW,
            f"Bookings are possible up to {BOOKING_WINDOW_DAYS} days ahead.",
        )
    if slot.start - now < MIN_LEAD_TIME:
        raise DomainError(ErrorCode.TOO_SOON, "Bookings need at least 60 minutes notice.")
    if slot.time.second or slot.time.microsecond or slot.time.minute % _GRID_MINUTES:
        raise DomainError(
            ErrorCode.SLOT_GRID,
            "Bookings start on a 15-minute grid.",
            suggested_time=_round_to_grid(slot.time).strftime("%H:%M"),
        )
    reason = repo.get_closure_reason(conn, slot.date)
    hours = repo.get_opening_hours(conn, slot.date.weekday())
    if (
        reason is not None
        or hours is None
        or hours.open_time is None
        or hours.last_seating is None
        or not hours.open_time <= slot.time <= hours.last_seating
    ):
        raise DomainError(
            ErrorCode.CLOSED,
            "The restaurant does not take bookings at that time.",
            closure_reason=reason,
            next_open=next_open(conn, slot, today),
        )


def _day_range(slot: Slot) -> tuple[str, str]:
    return slot.date.isoformat(), (slot.date + timedelta(days=2)).isoformat()


def find_table(
    conn: sqlite3.Connection, slot: Slot, party_size: int, zone: str = "any"
) -> repo.Table | None:
    """Best fit: the smallest free table that seats the party (ties broken by table id)."""
    taken = repo.taken_slots(conn, *_day_range(slot))
    keys = slot_keys(slot)
    candidates = sorted(
        (
            t
            for t in repo.get_tables(conn)
            if t.capacity >= party_size and (zone == "any" or t.zone == zone)
        ),
        key=lambda t: (t.capacity, t.id),
    )
    for table in candidates:
        if all((table.id, key) not in taken for key in keys):
            return table
    return None


def _is_bookable(conn: sqlite3.Connection, now: datetime, slot: Slot, party_size: int) -> bool:
    try:
        validate_request(conn, now, slot, party_size)
    except DomainError:
        return False
    return True


def find_alternatives(
    conn: sqlite3.Connection, now: datetime, slot: Slot, party_size: int, zone: str = "any"
) -> list[Slot]:
    """Up to 3 nearest free slots within ±90 min the same day, then the same time the next day."""
    found: list[Slot] = []
    steps = ALTERNATIVES_SPAN // SLOT_GRID
    base = datetime.combine(slot.date, slot.time)
    offsets = sorted(
        (i * SLOT_GRID for i in range(-steps, steps + 1) if i != 0),
        key=lambda d: (abs(d), d),
    )
    candidates = [base + d for d in offsets if (base + d).date() == slot.date]
    candidates.append(base + timedelta(days=1))
    for dt in candidates:
        if len(found) == MAX_ALTERNATIVES:
            break
        alt = Slot(dt.date(), dt.time())
        if _is_bookable(conn, now, alt, party_size) and find_table(conn, alt, party_size, zone):
            found.append(alt)
    return found
