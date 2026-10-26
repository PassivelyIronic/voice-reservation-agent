"""Load data/seed/*.yaml (validated with Pydantic) into SQLite.

    uv run python -m voice_agent.db.seed --reset [--reference-date YYYY-MM-DD]
    uv run python -m voice_agent.db.seed --check

Existing reservations are generated deterministically (random.Random(42)) relative to the
reference date, including a fully booked Friday evening for parties of 4+.
"""

import argparse
import json
import random
import sqlite3
import sys
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field

from voice_agent.config import get_settings
from voice_agent.db import repository as repo
from voice_agent.db.connection import connect, immediate, init_schema
from voice_agent.domain.availability import Slot, slot_keys
from voice_agent.domain.clock import RESTAURANT_TZ, SystemClock
from voice_agent.domain.ids import IdGenerator
from voice_agent.domain.policy import BOOKING_WINDOW_DAYS, RESERVATION_DURATION, SLOT_GRID

DEFAULT_SEED_DIR = Path("data/seed")
RESERVATIONS_RNG_SEED = 42

AllergenStatusValue = Literal["CONTAINS", "MAY_CONTAIN", "FREE"]
Category = Literal["starter", "pasta", "main", "dessert", "drink"]


class AllergenDef(BaseModel):
    code: str
    name_en: str
    name_pl: str


class IngredientDef(BaseModel):
    id: str
    name: str
    allergens: list[str] = Field(default_factory=list)  # validation only, not stored
    related_allergen_code: str | None = None
    related_note: str | None = None


class MenuItemDef(BaseModel):
    id: str
    name: str
    category: Category
    description: str
    price_pln: int
    is_available: bool = True
    aliases: list[str]
    ingredients: list[str]
    allergens: dict[str, AllergenStatusValue] | None = None


class MenuFile(BaseModel):
    verified_by: str
    verified_at: date
    intentionally_unverified: list[str]
    allergens: list[AllergenDef]
    ingredients: list[IngredientDef]
    items: list[MenuItemDef]


class TableDef(BaseModel):
    id: str
    capacity: int = Field(gt=0)
    zone: Literal["main", "window", "terrace"]


class HoursDef(BaseModel):
    weekday: int = Field(ge=0, le=6)
    open_time: time | None
    last_seating: time | None
    close_time: time | None


class ClosureDef(BaseModel):
    date: date
    reason: str


class SeedData(BaseModel):
    menu: MenuFile
    tables: list[TableDef]
    opening_hours: list[HoursDef]
    special_closures: list[ClosureDef]
    info: dict[str, str]


def _read(path: Path) -> Any:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def load_seed(seed_dir: Path = DEFAULT_SEED_DIR) -> SeedData:
    hours = _read(seed_dir / "hours.yaml")
    return SeedData.model_validate(
        {
            "menu": _read(seed_dir / "menu.yaml"),
            "tables": _read(seed_dir / "tables.yaml")["tables"],
            "opening_hours": hours["opening_hours"],
            "special_closures": hours["special_closures"],
            "info": _read(seed_dir / "info.yaml")["topics"],
        }
    )


# --- validator (--check) ---


def check_seed(seed: SeedData) -> list[str]:
    """Return a list of problems; empty means the seed is valid."""
    errors: list[str] = []
    menu = seed.menu
    codes = {a.code for a in menu.allergens}
    ingredients = {i.id: i for i in menu.ingredients}
    items = {i.id: i for i in menu.items}

    if len(codes) != 14:
        errors.append(f"expected 14 EU allergens, found {len(codes)}")
    for ing in menu.ingredients:
        for code in [*ing.allergens, *filter(None, [ing.related_allergen_code])]:
            if code not in codes:
                errors.append(f"ingredient {ing.id}: unknown allergen code {code!r}")
    for item in menu.items:
        for ing_id in item.ingredients:
            if ing_id not in ingredients:
                errors.append(f"item {item.id}: unknown ingredient {ing_id!r}")
        if item.allergens is None:
            continue
        missing = codes - item.allergens.keys()
        extra = item.allergens.keys() - codes
        if missing:
            errors.append(f"item {item.id}: allergen map misses {sorted(missing)}")
        if extra:
            errors.append(f"item {item.id}: allergen map has unknown codes {sorted(extra)}")
        implied = {
            code
            for ing_id in item.ingredients
            if ing_id in ingredients
            for code in ingredients[ing_id].allergens
        }
        # (a) every allergen implied by an ingredient is declared CONTAINS
        for code in sorted(implied):
            if item.allergens.get(code) != "CONTAINS":
                errors.append(
                    f"item {item.id}: ingredients contain {code} but status is "
                    f"{item.allergens.get(code)}"
                )
        # (b) every CONTAINS is backed by at least one ingredient
        for code, status in sorted(item.allergens.items()):
            if status == "CONTAINS" and code not in implied:
                errors.append(f"item {item.id}: {code} CONTAINS without a matching ingredient")
    # (c) items without an allergen map are exactly the intended ones
    unmapped = {i.id for i in menu.items if i.allergens is None}
    if unmapped != set(menu.intentionally_unverified):
        errors.append(
            f"items without allergen map {sorted(unmapped)} != intentionally_unverified "
            f"{sorted(menu.intentionally_unverified)}"
        )
    errors.extend(_check_required_fixtures(items, ingredients))
    return errors


def _check_required_fixtures(
    items: dict[str, MenuItemDef], ingredients: dict[str, IngredientDef]
) -> list[str]:
    """Edge cases the eval scenarios rely on (docs/plan/04-data-model.md, "Seed data")."""
    errors: list[str] = []

    def status(item_id: str, code: str) -> str | None:
        item = items.get(item_id)
        return item.allergens.get(code) if item and item.allergens else None

    pesto = items.get("pasta-pesto-genovese")
    if (
        pesto is None
        or not {"pine-nuts", "parmesan"} <= set(pesto.ingredients)
        or status(pesto.id, "nuts") != "FREE"
        or status(pesto.id, "milk") != "CONTAINS"
    ):
        errors.append(
            "pasta-pesto-genovese must have pine-nuts + parmesan, nuts FREE, milk CONTAINS"
        )
    pine = ingredients.get("pine-nuts")
    if pine is None or pine.related_allergen_code != "nuts" or not pine.related_note:
        errors.append("pine-nuts must have related_allergen_code 'nuts' and a related_note")
    if status("pesto-rosso", "nuts") != "CONTAINS":
        errors.append("pesto-rosso must have nuts CONTAINS")
    if not any(
        i.category == "dessert" and status(i.id, "nuts") == "MAY_CONTAIN" for i in items.values()
    ):
        errors.append("need a dessert with nuts MAY_CONTAIN")
    if not any(status(i, "peanuts") == "CONTAINS" and status(i, "nuts") == "FREE" for i in items):
        errors.append("need an item with peanuts CONTAINS and nuts FREE")
    if not any(not i.is_available for i in items.values()):
        errors.append("need a sold-out item (is_available: false)")
    special = items.get("special-of-the-week")
    if special is None or not special.ingredients or special.allergens is not None:
        errors.append("special-of-the-week must have ingredients and no allergen map")
    return errors


# --- loading ---

_NAMES = ["Anna", "Marek", "Kasia", "Tomasz", "Ola", "Piotr", "Ewa", "Jan", "Zofia", "Adam"]


def _insert_static(conn: sqlite3.Connection, seed: SeedData) -> None:
    def hhmm(t: time | None) -> str | None:
        return t.strftime("%H:%M") if t else None

    menu = seed.menu
    conn.executemany(
        "INSERT INTO opening_hours VALUES (?, ?, ?, ?)",
        [
            (h.weekday, hhmm(h.open_time), hhmm(h.last_seating), hhmm(h.close_time))
            for h in seed.opening_hours
        ],
    )
    conn.executemany(
        "INSERT INTO special_closures VALUES (?, ?)",
        [(c.date.isoformat(), c.reason) for c in seed.special_closures],
    )
    conn.executemany("INSERT INTO restaurant_info VALUES (?, ?)", list(seed.info.items()))
    conn.executemany(
        "INSERT INTO dining_tables VALUES (?, ?, ?)",
        [(t.id, t.capacity, t.zone) for t in seed.tables],
    )
    conn.executemany(
        "INSERT INTO allergens VALUES (?, ?, ?)",
        [(a.code, a.name_en, a.name_pl) for a in menu.allergens],
    )
    conn.executemany(
        "INSERT INTO ingredients VALUES (?, ?, ?, ?)",
        [(i.id, i.name, i.related_allergen_code, i.related_note) for i in menu.ingredients],
    )
    conn.executemany(
        "INSERT INTO menu_items VALUES (?, ?, ?, ?, ?, ?, ?)",
        [
            (
                i.id,
                i.name,
                i.category,
                i.description,
                i.price_pln * 100,
                int(i.is_available),
                json.dumps(i.aliases),
            )
            for i in menu.items
        ],
    )
    conn.executemany(
        "INSERT INTO menu_item_ingredients VALUES (?, ?)",
        [(i.id, ing) for i in menu.items for ing in i.ingredients],
    )
    conn.executemany(
        "INSERT INTO menu_item_allergens VALUES (?, ?, ?, ?, ?)",
        [
            (i.id, code, st, menu.verified_by, menu.verified_at.isoformat())
            for i in menu.items
            for code, st in (i.allergens or {}).items()
        ],
    )


def _first_friday_after(day: date) -> date:
    return day + timedelta(days=(4 - day.weekday() - 1) % 7 + 1)


def _insert_reservations(conn: sqlite3.Connection, seed: SeedData, reference: date) -> int:
    rng = random.Random(RESERVATIONS_RNG_SEED)
    ids = IdGenerator(rng)
    hours = {h.weekday: h for h in seed.opening_hours}
    closed = {c.date for c in seed.special_closures}
    taken: set[tuple[str, str]] = set()
    created_at = datetime.combine(reference, time(9, 0), tzinfo=RESTAURANT_TZ).isoformat()
    count = 0

    def book(table: TableDef, slot: Slot, party_size: int) -> None:
        nonlocal count
        keys = slot_keys(slot)
        if any((table.id, k) in taken for k in keys):
            return
        res_id = repo.insert_reservation(
            conn,
            repo.NewReservation(
                code=ids.reservation_code(),
                customer_name=rng.choice(_NAMES),
                phone=f"555{rng.randint(0, 9999):04d}",
                party_size=party_size,
                date=slot.date,
                start_time=slot.time,
                duration_min=RESERVATION_DURATION // timedelta(minutes=1),
                table_id=table.id,
                notes=None,
                source="seed",
                created_at=created_at,
            ),
        )
        repo.insert_slots(conn, table.id, keys, reservation_id=res_id)
        taken.update((table.id, k) for k in keys)
        count += 1

    # "No availability" scenario: every table for 4+ is booked at 19:45 on the first Friday,
    # so no 4+ party can start between 18:00 and 21:30.
    friday = _first_friday_after(reference)
    for table in seed.tables:
        if table.capacity >= 4:
            book(table, Slot(friday, time(19, 45)), table.capacity)

    # Sparse background bookings across the booking window.
    for offset in range(BOOKING_WINDOW_DAYS + 1):
        day = reference + timedelta(days=offset)
        h = hours.get(day.weekday())
        if day in closed or h is None or h.open_time is None or h.last_seating is None:
            continue
        start = datetime.combine(day, h.open_time)
        last = datetime.combine(day, h.last_seating)
        grid = [start + i * SLOT_GRID for i in range(int((last - start) / SLOT_GRID) + 1)]
        for _ in range(rng.randint(3, 8)):
            table = rng.choice(seed.tables)
            at = rng.choice(grid)
            book(table, Slot(day, at.time()), rng.randint(1, table.capacity))
    return count


def apply_seed(
    conn: sqlite3.Connection, seed: SeedData, reference: date, *, with_reservations: bool = True
) -> int:
    """Insert all seed data into an empty schema; returns the number of seeded reservations."""
    with immediate(conn):
        _insert_static(conn, seed)
        return _insert_reservations(conn, seed, reference) if with_reservations else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    parser.add_argument("--check", action="store_true", help="validate seed YAML and exit")
    parser.add_argument("--reset", action="store_true", help="delete and rebuild the database")
    parser.add_argument("--db", type=Path, default=None, help="database path (default: DB_PATH)")
    parser.add_argument("--seed-dir", type=Path, default=DEFAULT_SEED_DIR)
    parser.add_argument(
        "--reference-date",
        type=date.fromisoformat,
        default=None,
        help="date the generated reservations are relative to (default: today)",
    )
    args = parser.parse_args(argv)

    seed = load_seed(args.seed_dir)
    errors = check_seed(seed)
    if errors:
        print("Seed check FAILED:", *(f"  - {e}" for e in errors), sep="\n", file=sys.stderr)
        return 1
    print(f"Seed check OK: {len(seed.menu.items)} menu items, {len(seed.tables)} tables.")
    if args.check:
        return 0

    db_path: Path = args.db or get_settings().db_path
    if db_path.exists():
        if not args.reset:
            print(f"{db_path} exists; pass --reset to rebuild it.", file=sys.stderr)
            return 1
        db_path.unlink()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    reference: date = args.reference_date or SystemClock().now().date()
    conn = connect(db_path)
    try:
        init_schema(conn)
        count = apply_seed(conn, seed, reference)
    finally:
        conn.close()
    print(f"Seeded {db_path} with {count} reservations relative to {reference}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
