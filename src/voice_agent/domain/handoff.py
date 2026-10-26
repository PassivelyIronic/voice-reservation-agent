"""Handoff to restaurant staff: a ticket in handoff_tickets."""

import sqlite3
from typing import Literal

from voice_agent.db import repository as repo
from voice_agent.db.connection import immediate
from voice_agent.domain.clock import Clock

HandoffReason = Literal[
    "large_party",
    "allergen_unknown",
    "severe_allergy",
    "tool_failure",
    "customer_request",
    "complaint",
    "out_of_scope",
]


def create_ticket(
    conn: sqlite3.Connection,
    clock: Clock,
    conversation_id: str,
    reason: HandoffReason,
    summary: str,
) -> int:
    with immediate(conn):
        return repo.insert_handoff_ticket(
            conn, conversation_id, reason, summary.strip(), clock.now().isoformat()
        )
