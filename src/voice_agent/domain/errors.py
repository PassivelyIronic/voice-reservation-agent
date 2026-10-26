"""Typed domain errors. Codes match docs/plan/05-tools-spec.md."""

from enum import StrEnum


class ErrorCode(StrEnum):
    INVALID_DATE = "INVALID_DATE"
    IN_THE_PAST = "IN_THE_PAST"
    OUT_OF_WINDOW = "OUT_OF_WINDOW"
    TOO_SOON = "TOO_SOON"
    CLOSED = "CLOSED"
    LARGE_PARTY = "LARGE_PARTY"
    SLOT_GRID = "SLOT_GRID"
    NO_AVAILABILITY = "NO_AVAILABILITY"
    HOLD_NOT_FOUND = "HOLD_NOT_FOUND"
    HOLD_EXPIRED = "HOLD_EXPIRED"
    HOLD_FOREIGN = "HOLD_FOREIGN"
    CONFIRMATION_REQUIRED = "CONFIRMATION_REQUIRED"
    INVALID_PHONE = "INVALID_PHONE"
    SLOT_TAKEN = "SLOT_TAKEN"
    # Not listed in 05: unknown item_id passed to get_allergen_info.
    ITEM_NOT_FOUND = "ITEM_NOT_FOUND"


class DomainError(Exception):
    def __init__(self, code: ErrorCode, message: str, **details: object) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details: dict[str, object] = details
