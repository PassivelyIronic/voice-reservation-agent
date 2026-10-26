"""Verified restaurant facts: opening hours for a day and FAQ topics."""

import sqlite3
from dataclasses import dataclass
from datetime import date, time

from voice_agent.db import repository as repo


@dataclass(frozen=True)
class DayHours:
    date: date
    open_time: time | None  # None: closed that day
    last_seating: time | None
    close_time: time | None
    closure_reason: str | None


def hours_on(conn: sqlite3.Connection, day: date) -> DayHours:
    reason = repo.get_closure_reason(conn, day)
    hours = repo.get_opening_hours(conn, day.weekday())
    if reason is not None or hours is None or hours.open_time is None:
        return DayHours(day, None, None, None, reason)
    return DayHours(day, hours.open_time, hours.last_seating, hours.close_time, None)


def info_answer(conn: sqlite3.Connection, topic: str) -> str | None:
    return repo.get_info_answer(conn, topic)
