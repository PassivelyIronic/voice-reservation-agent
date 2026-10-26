"""Structured conversation state, maintained by the tools and rendered into the LLM context."""

from dataclasses import dataclass, field
from datetime import datetime

from voice_agent.dialogue.renderers import hold_readback, time_phrase
from voice_agent.domain.availability import Slot


@dataclass
class ConversationState:
    conversation_id: str
    turn: int = 0  # incremented once per user message
    party_size: int | None = None
    slot: Slot | None = None
    hold_id: str | None = None
    hold_expires_at: datetime | None = None
    hold_turns: dict[str, int] = field(default_factory=dict[str, int])  # hold_id -> turn created
    readback_given: bool = False
    customer_name: str | None = None
    confirmation_code: str | None = None
    # Allergen sentences approved by get_allergen_info, keyed by turn (read by the guard).
    allergen_approvals: dict[int, list[str]] = field(default_factory=dict[int, list[str]])
    guard_tokens: list[str] = field(default_factory=list[str])
    ended: bool = False

    def start_turn(self) -> None:
        self.turn += 1
        for turn in [t for t in self.allergen_approvals if t < self.turn - 1]:
            del self.allergen_approvals[turn]

    def record_hold(self, hold_id: str, slot: Slot, party_size: int, expires_at: datetime) -> None:
        self.hold_id = hold_id
        self.slot = slot
        self.party_size = party_size
        self.hold_expires_at = expires_at
        self.hold_turns[hold_id] = self.turn
        self.readback_given = True

    def clear_hold(self) -> None:
        self.hold_id = None
        self.hold_expires_at = None
        self.readback_given = False

    def approve_allergen_answer(self, sentences: list[str]) -> str:
        """Register approved sentences for this turn and return a guard token."""
        self.allergen_approvals.setdefault(self.turn, []).extend(sentences)
        token = f"AG-{self.turn}-{len(self.guard_tokens) + 1}"
        self.guard_tokens.append(token)
        return token

    def approved_sentences(self) -> list[str]:
        """Approvals from this turn and the previous one (a follow-up about the same dish)."""
        return [s for t in (self.turn - 1, self.turn) for s in self.allergen_approvals.get(t, [])]

    def render(self, now: datetime) -> str:
        lines = [f"BOOKING STATE (turn {self.turn})"]
        if self.confirmation_code:
            lines.append(f"- Confirmed booking, code {self.confirmation_code}.")
        if self.hold_id and self.slot and self.party_size and self.hold_expires_at:
            seconds = max(0, int((self.hold_expires_at - now).total_seconds()))
            lines.append(
                f"- Active hold {self.hold_id}: {hold_readback(self.slot, self.party_size)} "
                f"({time_phrase(self.slot.time)}), expires in {seconds} s."
            )
            if self.hold_turns.get(self.hold_id) == self.turn:
                lines.append("- The hold was placed this turn: read it back and wait for a yes.")
            else:
                lines.append("- Readback already given; confirm only after an explicit yes.")
        elif not self.confirmation_code:
            lines.append("- No active hold.")
        if self.customer_name:
            lines.append(f"- Customer name: {self.customer_name}.")
        return "\n".join(lines)
