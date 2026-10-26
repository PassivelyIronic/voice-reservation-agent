from datetime import date, time

import pytest

from voice_agent.dialogue import renderers
from voice_agent.domain.allergens import lookup_allergens
from voice_agent.domain.availability import Slot

TUESDAY_1930 = Slot(date(2026, 10, 27), time(19, 30))


@pytest.mark.parametrize(
    ("t", "spoken"),
    [
        (time(19, 30), "7:30 PM"),
        (time(21, 0), "9 PM"),
        (time(12, 0), "noon"),
        (time(11, 15), "11:15 AM"),
    ],
)
def test_time_phrase(t: time, spoken: str) -> None:
    assert renderers.time_phrase(t) == spoken


@pytest.mark.parametrize(
    ("day", "spoken"), [(1, "1st"), (2, "2nd"), (3, "3rd"), (11, "11th"), (22, "22nd")]
)
def test_ordinal(day: int, spoken: str) -> None:
    assert renderers.ordinal(day) == spoken


def test_hold_readback_matches_spec_example() -> None:
    assert (
        renderers.hold_readback(TUESDAY_1930, 4)
        == "a table for 4 on Tuesday, October 27th at 7:30 PM"
    )


def test_confirmation_spells_code() -> None:
    text = renderers.confirmation_readback(TUESDAY_1930, 4, "Anna", "OV-4F2K")
    assert text == (
        "You're booked: a table for 4 on Tuesday, October 27th at 7:30 PM under the name Anna. "
        "Your confirmation code is O-V, 4, F, 2, K."
    )


def answer(db, item_id: str, *asked: str) -> tuple[str, bool]:
    return renderers.allergen_answer(lookup_allergens(db, item_id, list(asked)))


def test_pesto_nuts_answer(db) -> None:
    text, offer = answer(db, "pasta-pesto-genovese", "nuts")
    assert text.startswith(
        "According to our verified allergen records, the Pesto Genovese contains no tree nuts."
    )
    assert "It does contain pine nuts." in text
    assert text.endswith(renderers.SEVERE_ALLERGY_OFFER)
    assert offer


def test_contains_has_no_offer(db) -> None:
    text, offer = answer(db, "spiedini-satay", "peanuts")
    assert text == "The Chicken Skewers with Peanut Sauce contains peanuts."
    assert not offer


def test_may_contain_offers_staff(db) -> None:
    text, offer = answer(db, "tiramisu", "nuts")
    assert "may contain traces of tree nuts" in text
    assert offer and text.endswith(renderers.STAFF_OFFER)


def test_unknown_never_claims(db) -> None:
    text, offer = answer(db, "special-of-the-week", "gluten")
    assert "don't have verified allergen information" in text
    assert "contains" not in text
    assert offer


def test_untracked_allergen(db) -> None:
    text, offer = answer(db, "pasta-pesto-genovese", "garlic")
    assert text.startswith("We only track the 14 major allergens")
    assert offer


def test_several_allergens_in_one_answer(db) -> None:
    text, _ = answer(db, "pasta-pesto-genovese", "dairy", "gluten")
    assert "contains milk" in text and "contains gluten" in text


def test_split_sentences() -> None:
    assert renderers.split_sentences("One. Two? Three!") == ["One.", "Two?", "Three!"]
