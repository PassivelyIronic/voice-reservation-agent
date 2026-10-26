"""Deterministic vocabulary for AllergenClaimGuard (docs/plan/06-dialogue-guardrails.md)."""

import re
from collections.abc import Iterable

from voice_agent.domain.allergens import SYNONYMS

# A sentence must match an approved spoken_answer sentence at least this closely to pass.
APPROVED_MATCH_RATIO = 90.0

REPLACEMENT_TEXT = (
    "I can't confirm allergen details without checking our verified records. "
    "Would you like me to check, or connect you with our staff?"
)

# Statements about the presence or absence of an allergen.
CLAIM_MARKERS = (
    r"contains?",
    r"containing",
    r"free",
    r"no",
    r"not",
    r"none",
    r"without",
    r"safe",
    r"traces?",
    r"made with",
    r"fine for",
    r"allergy[- ]friendly",
    r"includes?",
    r"has",  # not "have": "I understand you have a nut allergy." is not a claim
    r"doesn't",
    r"does not",
    r"isn't",
    r"is in",
    r"there's",
    r"there are",
)

# Absolute guarantees: replaced even when an approved answer exists (06, step 4).
ABSOLUTE_GUARANTEES = (
    r"safe for you",
    r"safe to eat",
    r"completely safe",
    r"perfectly safe",
    r"totally safe",
    r"you'll be fine",
    r"you will be fine",
    r"no risk",
    r"risk[- ]free",
    r"nothing to worry about",
    r"guaranteed?",
    r"100 ?%",
)

# Food-safety guarantees that are replaced even without an allergen word in the same sentence
# ("Don't worry, it's safe for you."), because the allergen is usually named a sentence earlier.
STANDALONE_GUARANTEES = ABSOLUTE_GUARANTEES[:10]

# Words that are mentions but not claims by themselves (the caller's condition).
_EXTRA_TERMS = ("allergen", "allergens", "pine nuts", "pinoli")


def _alternation(patterns: Iterable[str]) -> re.Pattern[str]:
    return re.compile(r"\b(?:" + "|".join(patterns) + r")\b", re.IGNORECASE)


class Lexicon:
    def __init__(self, extra_terms: Iterable[str] = ()) -> None:
        terms = {*SYNONYMS, *_EXTRA_TERMS, *(t.lower() for t in extra_terms)}
        ordered = sorted(terms, key=len, reverse=True)  # longest first: "tree nuts" before "nuts"
        self.mentions = _alternation(re.escape(t) for t in ordered)
        self.claims = _alternation(CLAIM_MARKERS)
        self.absolute = _alternation(ABSOLUTE_GUARANTEES)
        self.standalone = _alternation(STANDALONE_GUARANTEES)


def normalize(text: str) -> str:
    return " ".join(re.sub(r"[^\w\s']", " ", text.lower()).split())
