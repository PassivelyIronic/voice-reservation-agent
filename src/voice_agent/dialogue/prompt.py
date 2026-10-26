"""System prompt (docs/plan/06-dialogue-guardrails.md, draft v0) and the per-turn state message."""

from pathlib import Path
from typing import Any

from voice_agent.dialogue.state import ConversationState
from voice_agent.domain.clock import RESTAURANT_TZ, Clock

PROMPT_PATH = Path(__file__).parent / "prompts" / "system.md"
STATE_PREFIX = "BOOKING STATE"


def build_system_prompt(clock: Clock) -> str:
    now = clock.now().astimezone(RESTAURANT_TZ)
    return PROMPT_PATH.read_text(encoding="utf-8").format(
        today_weekday=f"{now:%A}",
        today_date=f"{now:%Y-%m-%d}",
        now_time=f"{now:%H:%M}",
        timezone=str(RESTAURANT_TZ),
    )


def state_message(state: ConversationState, clock: Clock) -> dict[str, Any]:
    return {"role": "developer", "content": state.render(clock.now())}


def is_state_message(message: Any) -> bool:
    return (
        isinstance(message, dict)
        and message.get("role") == "developer"  # type: ignore[union-attr]
        and str(message.get("content", "")).startswith(STATE_PREFIX)  # type: ignore[union-attr]
    )
