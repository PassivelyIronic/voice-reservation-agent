"""Injected time source. The only place allowed to read the system clock."""

from datetime import UTC, datetime, timedelta
from typing import Protocol
from zoneinfo import ZoneInfo

RESTAURANT_TZ = ZoneInfo("Europe/Warsaw")


class Clock(Protocol):
    def now(self) -> datetime:
        """Current time, timezone-aware, in the restaurant's timezone."""
        ...


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(RESTAURANT_TZ)


class FrozenClock:
    """Fixed time for tests and eval scenarios; `advance` moves it by absolute time."""

    def __init__(self, at: datetime) -> None:
        if at.tzinfo is None:
            raise ValueError("FrozenClock needs a timezone-aware datetime")
        self._at = at.astimezone(RESTAURANT_TZ)

    def now(self) -> datetime:
        return self._at

    def advance(self, delta: timedelta) -> None:
        self._at = (self._at.astimezone(UTC) + delta).astimezone(RESTAURANT_TZ)
