"""AllergenClaimGuard: rule-based check of every bot sentence before it reaches TTS (or the CLI).

Algorithm per sentence (docs/plan/06-dialogue-guardrails.md):
1. no allergen mention -> pass; 2. mention without a claim marker -> pass;
3. absolute guarantee -> replace (even with an approved answer);
4. close match (rapidfuzz ratio >= 90) to an approved spoken_answer sentence -> pass;
5. otherwise -> replace with a safe template and log guard.triggered.
Food-safety guarantees ("it's safe for you") are replaced even without a mention in the same
sentence, since the allergen is usually named in the previous one.
"""

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Literal

from loguru import logger
from pipecat.frames.frames import (
    Frame,
    InterruptionFrame,
    LLMFullResponseEndFrame,
    LLMTextFrame,
)
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from rapidfuzz import fuzz

from voice_agent.guards.lexicon import APPROVED_MATCH_RATIO, REPLACEMENT_TEXT, Lexicon, normalize

Reason = Literal["no_mention", "no_claim", "approved", "absolute", "unapproved"]

# A sentence ends at . ! or ? followed by whitespace; the whitespace stays with the sentence.
_SENTENCE_BOUNDARY = re.compile(r"[.!?]+[\"')\]]*\s+")


@dataclass(frozen=True)
class Verdict:
    allowed: bool
    reason: Reason


def check_sentence(sentence: str, approved: Sequence[str], lexicon: Lexicon) -> Verdict:
    if lexicon.standalone.search(sentence):
        return Verdict(False, "absolute")
    if not lexicon.mentions.search(sentence):
        return Verdict(True, "no_mention")
    if not lexicon.claims.search(sentence) and not lexicon.absolute.search(sentence):
        return Verdict(True, "no_claim")
    if lexicon.absolute.search(sentence):
        return Verdict(False, "absolute")
    candidate = normalize(sentence)
    if any(fuzz.ratio(candidate, normalize(a)) >= APPROVED_MATCH_RATIO for a in approved):
        return Verdict(True, "approved")
    return Verdict(False, "unapproved")


class AllergenClaimGuard(FrameProcessor):
    """Buffers LLM text to sentence boundaries and replaces unverified allergen claims."""

    def __init__(
        self,
        approved: Callable[[], Sequence[str]],
        lexicon: Lexicon | None = None,
        **kwargs: object,
    ) -> None:
        super().__init__(**kwargs)  # type: ignore[arg-type]
        self._approved = approved
        self._lexicon = lexicon or Lexicon()
        self._buffer = ""
        self._replaced_in_response = False
        self.triggered_count = 0

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)

        if isinstance(frame, InterruptionFrame):
            self._buffer = ""  # barge-in: drop unspoken text without saying it
            self._replaced_in_response = False
            await self.push_frame(frame, direction)
        elif isinstance(frame, LLMTextFrame) and direction == FrameDirection.DOWNSTREAM:
            self._buffer += frame.text
            await self._push_complete_sentences()
        elif isinstance(frame, LLMFullResponseEndFrame):
            await self._flush()
            self._replaced_in_response = False
            await self.push_frame(frame, direction)
        else:
            await self.push_frame(frame, direction)

    async def _push_complete_sentences(self) -> None:
        end = 0
        for match in _SENTENCE_BOUNDARY.finditer(self._buffer):
            end = match.end()
        if end:
            complete, self._buffer = self._buffer[:end], self._buffer[end:]
            for sentence in _split_keep_spacing(complete):
                await self._emit(sentence)

    async def _flush(self) -> None:
        if self._buffer:
            remainder, self._buffer = self._buffer, ""
            for sentence in _split_keep_spacing(remainder):
                await self._emit(sentence)

    async def _emit(self, sentence: str) -> None:
        if not sentence.strip():
            await self.push_frame(LLMTextFrame(sentence))
            return
        verdict = check_sentence(sentence, self._approved(), self._lexicon)
        if not verdict.allowed:
            self.triggered_count += 1
            logger.warning(f"guard.triggered reason={verdict.reason} sentence={sentence.strip()!r}")
            if self._replaced_in_response:
                return  # the safe template was already said in this response
            self._replaced_in_response = True
            trailing = sentence[len(sentence.rstrip()) :]
            sentence = REPLACEMENT_TEXT + (trailing or " ")
        await self.push_frame(LLMTextFrame(sentence))


def _split_keep_spacing(text: str) -> list[str]:
    parts: list[str] = []
    start = 0
    for match in _SENTENCE_BOUNDARY.finditer(text):
        parts.append(text[start : match.end()])
        start = match.end()
    if start < len(text):
        parts.append(text[start:])
    return parts
