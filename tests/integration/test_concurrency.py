"""Two callers race for the last table: exactly one gets it (UNIQUE(table_id, slot_start))."""

import random
import threading
from pathlib import Path

import pytest

from tests.conftest import FROZEN_NOW, REFERENCE_DATE
from voice_agent.db.connection import connect, init_schema
from voice_agent.db.seed import SeedData, apply_seed
from voice_agent.domain.clock import FrozenClock
from voice_agent.domain.ids import IdGenerator
from voice_agent.domain.reservations import check_availability

pytestmark = pytest.mark.integration


def test_last_table_goes_to_exactly_one_caller(tmp_path: Path, seed_data: SeedData) -> None:
    db_path = tmp_path / "race.db"
    setup = connect(db_path)
    init_schema(setup)
    apply_seed(setup, seed_data, REFERENCE_DATE, with_reservations=False)
    setup.execute("DELETE FROM dining_tables WHERE id != 'T12'")  # one table left
    setup.close()

    barrier = threading.Barrier(2)
    results: dict[str, bool] = {}
    errors: list[BaseException] = []

    def caller(name: str) -> None:
        conn = connect(db_path)
        try:
            # Same RNG seed in both threads: hold ids collide unless uniqueness is enforced.
            ids = IdGenerator(random.Random(7))
            barrier.wait()
            result = check_availability(
                conn, FrozenClock(FROZEN_NOW), ids, name, "2026-10-27", "19:30", 6
            )
            results[name] = result.available
        except BaseException as exc:
            errors.append(exc)
        finally:
            conn.close()

    threads = [threading.Thread(target=caller, args=(n,)) for n in ("caller-a", "caller-b")]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)

    assert errors == []
    assert sorted(results.values()) == [False, True]
