import copy

from tests.conftest import open_db
from voice_agent.db.seed import MenuItemDef, SeedData, check_seed
from voice_agent.domain.reservations import check_availability


def item(seed: SeedData, item_id: str) -> MenuItemDef:
    return next(i for i in seed.menu.items if i.id == item_id)


def allergen_map(seed: SeedData, item_id: str) -> dict[str, str]:
    allergens = item(seed, item_id).allergens
    assert allergens is not None
    return allergens  # type: ignore[return-value]


def test_repo_seed_passes_check(seed_data) -> None:
    assert check_seed(seed_data) == []


def test_menu_and_tables_shape(seed_data) -> None:
    assert len(seed_data.menu.items) == 25
    assert sorted(t.capacity for t in seed_data.tables) == [2, 2, 4, 4, 4, 4, 4, 4, 6, 6, 6, 8]


def test_rule_a_ingredient_allergen_must_be_contains(seed_data) -> None:
    seed = copy.deepcopy(seed_data)
    allergen_map(seed, "pasta-pesto-genovese")["milk"] = "FREE"
    assert any("ingredients contain milk" in e for e in check_seed(seed))


def test_rule_b_contains_needs_an_ingredient(seed_data) -> None:
    seed = copy.deepcopy(seed_data)
    allergen_map(seed, "panna-cotta")["fish"] = "CONTAINS"
    assert any("fish CONTAINS without" in e for e in check_seed(seed))


def test_rule_c_unmapped_items_must_be_intended(seed_data) -> None:
    seed = copy.deepcopy(seed_data)
    item(seed, "tiramisu").allergens = None
    assert any("intentionally_unverified" in e for e in check_seed(seed))


def test_mapped_items_list_all_14_allergens(seed_data) -> None:
    seed = copy.deepcopy(seed_data)
    del allergen_map(seed, "affogato")["lupin"]
    assert any("misses ['lupin']" in e for e in check_seed(seed))


def test_seeded_friday_evening_is_full_for_four(seeded_db, clock, ids) -> None:
    for at in ("19:00", "19:30", "20:00", "20:30"):
        assert not check_availability(seeded_db, clock, ids, "x", "2026-10-30", at, 4).available


def test_flagship_scenario_slot_is_free(seeded_db, clock, ids) -> None:
    assert check_availability(seeded_db, clock, ids, "x", "2026-10-27", "19:30", 4).available


def test_reservations_are_deterministic(seeded_db, seed_data) -> None:
    other = open_db(seed_data, with_reservations=True)
    query = "SELECT code, date, start_time, table_id FROM reservations ORDER BY id"
    assert [tuple(r) for r in seeded_db.execute(query)] == [tuple(r) for r in other.execute(query)]
