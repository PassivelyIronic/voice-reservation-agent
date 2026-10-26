"""Customer-facing precise text. Readbacks and allergen answers come only from these templates."""

import re
from datetime import date, time

from voice_agent.domain.allergens import AllergenLookup, AllergenResult
from voice_agent.domain.availability import Slot
from voice_agent.domain.info import DayHours

ALLERGEN_NAMES = {
    "gluten": "gluten",
    "crustaceans": "crustaceans",
    "eggs": "eggs",
    "fish": "fish",
    "peanuts": "peanuts",
    "soy": "soy",
    "milk": "milk",
    "nuts": "tree nuts",
    "celery": "celery",
    "mustard": "mustard",
    "sesame": "sesame",
    "sulphites": "sulphites",
    "lupin": "lupin",
    "molluscs": "molluscs",
}

HANDOFF_ANNOUNCEMENT = "I'm passing you to our staff now. Thank you for your patience."
SEVERE_ALLERGY_OFFER = "If your allergy is severe, I can connect you with our staff."
STAFF_OFFER = "I can connect you with our staff if you'd like."


_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


def split_sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENTENCE_END.split(text) if s.strip()]


def ordinal(n: int) -> str:
    suffix = "th" if 11 <= n % 100 <= 13 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def day_phrase(d: date) -> str:
    """'Tuesday, October 27th'."""
    return f"{d:%A}, {d:%B} {ordinal(d.day)}"


def time_phrase(t: time) -> str:
    """12-hour clock as spoken: 'noon', '9 PM', '7:30 PM'."""
    if (t.hour, t.minute) == (12, 0):
        return "noon"
    if (t.hour, t.minute) == (0, 0):
        return "midnight"
    hour = t.hour % 12 or 12
    suffix = "AM" if t.hour < 12 else "PM"
    return f"{hour} {suffix}" if t.minute == 0 else f"{hour}:{t.minute:02d} {suffix}"


def slot_readback(slot: Slot) -> str:
    return f"{day_phrase(slot.date)} at {time_phrase(slot.time)}"


def hold_readback(slot: Slot, party_size: int) -> str:
    return f"a table for {party_size} on {slot_readback(slot)}"


def spell_code(code: str) -> str:
    """'OV-4F2K' -> 'O-V, 4, F, 2, K'."""
    prefix, _, rest = code.partition("-")
    return ", ".join(["-".join(prefix), *rest])


def confirmation_readback(slot: Slot, party_size: int, name: str, code: str) -> str:
    return (
        f"You're booked: {hold_readback(slot, party_size)} under the name {name}. "
        f"Your confirmation code is {spell_code(code)}."
    )


def opening_hours_answer(hours: DayHours) -> str:
    when = f"On {day_phrase(hours.date)}"
    if hours.open_time is None or hours.close_time is None or hours.last_seating is None:
        if hours.closure_reason:
            return f"{when} we're closed. {hours.closure_reason}."
        return f"{when} we're closed."
    return (
        f"{when} we're open from {time_phrase(hours.open_time)} to "
        f"{time_phrase(hours.close_time)}; the last seating is at "
        f"{time_phrase(hours.last_seating)}."
    )


def next_open_readback(next_open: dict[str, str]) -> str:
    day = date.fromisoformat(next_open["date"])
    opens = time.fromisoformat(next_open["open_time"])
    last = time.fromisoformat(next_open["last_seating"])
    return (
        f"{day_phrase(day)}, from {time_phrase(opens)}, with the last seating at "
        f"{time_phrase(last)}"
    )


def _allergen_sentences(item_name: str, result: AllergenResult) -> list[str]:
    related = [
        f"It does contain {r.name}." + (f" {r.note}" if r.note else "")
        for r in result.related_ingredients
    ]
    if result.code is None:
        if related:
            return related
        return [
            "We only track the 14 major allergens in our verified records, "
            f"so I can't confirm anything about {result.asked} for the {item_name}."
        ]
    name = ALLERGEN_NAMES[result.code]
    if result.status == "CONTAINS":
        return [f"The {item_name} contains {name}."]
    if result.status == "MAY_CONTAIN":
        return [
            f"The {item_name} may contain traces of {name}; "
            "it's prepared in a kitchen that handles it."
        ]
    if result.status == "FREE":
        return [
            f"According to our verified allergen records, the {item_name} contains no {name}.",
            *related,
        ]
    return [
        f"I don't have verified allergen information for the {item_name}, so I can't confirm it."
    ]


def _needs_handoff_offer(result: AllergenResult) -> bool:
    if result.code is None or result.status in ("UNKNOWN", "MAY_CONTAIN"):
        return True
    return result.status == "FREE" and bool(result.related_ingredients)


def allergen_answer(lookup: AllergenLookup) -> tuple[str, bool]:
    """Spoken answer for every asked allergen, plus whether it ends with a handoff offer."""
    sentences: list[str] = []
    for result in lookup.results:
        for sentence in _allergen_sentences(lookup.item_name, result):
            if sentence not in sentences:
                sentences.append(sentence)
    results = lookup.results
    offer = any(_needs_handoff_offer(r) for r in results)
    if offer:
        free_with_related = all(r.status in ("FREE", "CONTAINS") for r in results)
        sentences.append(SEVERE_ALLERGY_OFFER if free_with_related else STAFF_OFFER)
    return " ".join(sentences), offer
