"""Hold ids and reservation codes from an injected RNG, so seeded runs are reproducible."""

import random

from voice_agent.domain.policy import CODE_ALPHABET, CODE_LENGTH


class IdGenerator:
    def __init__(self, rng: random.Random) -> None:
        self._rng = rng

    def hold_id(self) -> str:
        return f"H-{self._rng.getrandbits(16):04X}"

    def reservation_code(self) -> str:
        return "OV-" + "".join(self._rng.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH))
