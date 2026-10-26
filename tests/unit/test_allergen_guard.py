"""AllergenClaimGuard: ~20 positive/negative sentences + processor behaviour."""

import pytest
from pipecat.frames.frames import Frame, InterruptionFrame, LLMFullResponseEndFrame, LLMTextFrame
from pipecat.tests.utils import SleepFrame, run_test

from voice_agent.guards.allergen_guard import AllergenClaimGuard, check_sentence
from voice_agent.guards.lexicon import REPLACEMENT_TEXT, Lexicon

PESTO_APPROVED = [
    "According to our verified allergen records, the Pesto Genovese contains no tree nuts.",
    "It does contain pine nuts.",
    "Pine nuts are not classed as tree nuts, but some people with nut allergies react to them.",
    "If your allergy is severe, I can connect you with our staff.",
]
LEXICON = Lexicon()

PASS_WITHOUT_TOOL = [
    "Sure, a table for four tomorrow at 7:30 PM.",
    "I understand you have a nut allergy.",
    "Let me check the allergen records for the pesto.",
    "Which dish would you like me to check for peanuts?",
    "Our address is 12 Zielona Street.",
    "I'll note the nut allergy on your booking.",
]
BLOCK_WITHOUT_TOOL = [
    "The pesto contains no nuts.",
    "The tiramisu is nut-free.",
    "Yes, the carbonara is gluten free.",
    "The risotto doesn't have any dairy.",
    "There are no peanuts in the satay.",
    "The burrata is made with milk.",
    "The panna cotta may contain traces of tree nuts.",
]
ALWAYS_BLOCK = [
    "Don't worry, it's safe for you.",
    "You'll be fine with the pesto, there are no nuts.",
    "It's completely safe to eat with a dairy allergy.",
    "I can guarantee there are no nuts in it.",
]


@pytest.mark.parametrize("sentence", PASS_WITHOUT_TOOL)
def test_passes_when_no_allergen_claim(sentence: str) -> None:
    assert check_sentence(sentence, [], LEXICON).allowed


@pytest.mark.parametrize("sentence", BLOCK_WITHOUT_TOOL)
def test_blocks_unverified_claims(sentence: str) -> None:
    verdict = check_sentence(sentence, [], LEXICON)
    assert not verdict.allowed and verdict.reason == "unapproved"


@pytest.mark.parametrize("sentence", ALWAYS_BLOCK)
def test_blocks_guarantees_even_with_approved_answer(sentence: str) -> None:
    assert not check_sentence(sentence, PESTO_APPROVED, LEXICON).allowed


@pytest.mark.parametrize("sentence", PESTO_APPROVED[:3])
def test_passes_tool_answer_verbatim(sentence: str) -> None:
    assert check_sentence(sentence, PESTO_APPROVED, LEXICON).reason == "approved"


def test_passes_tool_answer_with_minor_rewording() -> None:
    sentence = (
        "According to our verified allergen records the Pesto Genovese contains no tree nuts!"
    )
    assert check_sentence(sentence, PESTO_APPROVED, LEXICON).allowed


def test_blocks_paraphrase_that_changes_meaning() -> None:
    sentence = "The Pesto Genovese contains no nuts at all, pine nuts included."
    assert not check_sentence(sentence, PESTO_APPROVED, LEXICON).allowed


def test_approval_for_one_dish_does_not_cover_another() -> None:
    sentence = "According to our verified allergen records, the Tiramisu contains no tree nuts."
    assert not check_sentence(sentence, PESTO_APPROVED, LEXICON).allowed


# --- processor (real process_frame via pipecat's run_test) ---


async def guard_output(frames: list[Frame], approved: list[str]) -> tuple[str, AllergenClaimGuard]:
    guard = AllergenClaimGuard(approved=lambda: approved)
    down, _ = await run_test(guard, frames_to_send=frames)
    return "".join(f.text for f in down if isinstance(f, LLMTextFrame)), guard


async def test_sentence_split_across_frames_is_checked_whole() -> None:
    frames = [LLMTextFrame(t) for t in ["The pes", "to contains ", "no nuts. Anything", " else?"]]
    text, guard = await guard_output([*frames, LLMFullResponseEndFrame()], [])
    assert text == REPLACEMENT_TEXT + " Anything else?"
    assert guard.triggered_count == 1


async def test_approved_answer_passes_unchanged() -> None:
    answer = " ".join(PESTO_APPROVED)
    text, guard = await guard_output(
        [LLMTextFrame(answer), LLMFullResponseEndFrame()], PESTO_APPROVED
    )
    assert text == answer
    assert guard.triggered_count == 0


async def test_template_is_said_once_per_response() -> None:
    frames = [LLMTextFrame("The pesto has no nuts. The tiramisu has no nuts. Bye.")]
    text, guard = await guard_output([*frames, LLMFullResponseEndFrame()], [])
    assert text == REPLACEMENT_TEXT + " Bye."
    assert guard.triggered_count == 2


async def test_interruption_drops_unspoken_buffer() -> None:
    frames: list[Frame] = [
        LLMTextFrame("The pesto contains no"),
        SleepFrame(sleep=0.05),  # let the text reach the buffer before the barge-in
        InterruptionFrame(),
        LLMFullResponseEndFrame(),
    ]
    text, _ = await guard_output(frames, [])
    assert text == ""
