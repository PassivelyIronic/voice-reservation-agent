from datetime import timedelta

from voice_agent.dialogue.prompt import build_system_prompt, is_state_message, state_message
from voice_agent.dialogue.state import ConversationState
from voice_agent.domain.availability import Slot, parse_slot
from voice_agent.domain.policy import HOLD_TTL


def test_system_prompt_has_frozen_date_and_rules(clock) -> None:
    prompt = build_system_prompt(clock)
    assert "Today is Monday, 2026-10-26. Current time: 13:00 (Europe/Warsaw)." in prompt
    assert 'Speak "spoken_answer" exactly as given.' in prompt
    assert "{" not in prompt


def test_state_message_reflects_hold(clock) -> None:
    state = ConversationState("c")
    state.start_turn()
    slot: Slot = parse_slot("2026-10-27", "19:30")
    state.record_hold("H-0001", slot, 4, clock.now() + HOLD_TTL)
    message = state_message(state, clock)
    assert is_state_message(message)
    assert (
        "Active hold H-0001: a table for 4 on Tuesday, October 27th at 7:30 PM"
        in message["content"]
    )
    assert "expires in 300 s" in message["content"]
    assert "placed this turn" in message["content"]

    state.start_turn()
    clock.advance(timedelta(seconds=60))
    later = state_message(state, clock)["content"]
    assert "expires in 240 s" in later
    assert "Readback already given" in later


def test_allergen_approvals_last_two_turns() -> None:
    state = ConversationState("c")
    state.start_turn()
    state.approve_allergen_answer(["A."])
    state.start_turn()
    assert state.approved_sentences() == ["A."]
    state.start_turn()
    assert state.approved_sentences() == []


def test_user_messages_are_not_state_messages() -> None:
    assert not is_state_message({"role": "user", "content": "BOOKING STATE please"})
