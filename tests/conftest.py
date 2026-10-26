import random
import sqlite3
from collections.abc import Iterator
from datetime import date, datetime
from pathlib import Path

import pytest

from voice_agent.db.connection import connect, init_schema
from voice_agent.db.seed import SeedData, apply_seed, load_seed
from voice_agent.domain.clock import RESTAURANT_TZ, FrozenClock
from voice_agent.domain.ids import IdGenerator

SEED_DIR = Path(__file__).resolve().parents[1] / "data" / "seed"
# Frozen "now" of the eval scenarios (docs/plan/07-evaluation.md): Monday, restaurant closed.
REFERENCE_DATE = date(2026, 10, 26)
FROZEN_NOW = datetime(2026, 10, 26, 13, 0, tzinfo=RESTAURANT_TZ)


@pytest.fixture(scope="session")
def seed_data() -> SeedData:
    return load_seed(SEED_DIR)


@pytest.fixture
def clock() -> FrozenClock:
    return FrozenClock(FROZEN_NOW)


@pytest.fixture
def ids() -> IdGenerator:
    return IdGenerator(random.Random(0))


def open_db(seed: SeedData, *, with_reservations: bool) -> sqlite3.Connection:
    conn = connect(":memory:")
    init_schema(conn)
    apply_seed(conn, seed, REFERENCE_DATE, with_reservations=with_reservations)
    return conn


@pytest.fixture
def db(seed_data: SeedData) -> Iterator[sqlite3.Connection]:
    """Seeded restaurant with no existing reservations."""
    conn = open_db(seed_data, with_reservations=False)
    yield conn
    conn.close()


@pytest.fixture
def seeded_db(seed_data: SeedData) -> Iterator[sqlite3.Connection]:
    """Seeded restaurant including the generated reservations."""
    conn = open_db(seed_data, with_reservations=True)
    yield conn
    conn.close()
