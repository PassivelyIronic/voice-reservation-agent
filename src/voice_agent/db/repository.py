"""Thin SQL access layer. No business rules here: those live in voice_agent.domain."""

import json
import sqlite3
from dataclasses import dataclass
from datetime import date, time


@dataclass(frozen=True)
class Table:
    id: str
    capacity: int
    zone: str


@dataclass(frozen=True)
class OpeningHours:
    weekday: int
    open_time: time | None
    last_seating: time | None
    close_time: time | None


@dataclass(frozen=True)
class Hold:
    id: str
    table_id: str
    date: date
    start_time: time
    party_size: int
    conversation_id: str
    expires_at: str
    status: str


@dataclass(frozen=True)
class NewReservation:
    code: str
    customer_name: str
    phone: str
    party_size: int
    date: date
    start_time: time
    duration_min: int
    table_id: str
    notes: str | None
    source: str
    created_at: str


@dataclass(frozen=True)
class MenuItem:
    id: str
    name: str
    category: str
    description: str
    price_pln: int
    is_available: bool
    aliases: tuple[str, ...]


@dataclass(frozen=True)
class Ingredient:
    id: str
    name: str
    related_allergen_code: str | None
    related_note: str | None


def _time(value: str | None) -> time | None:
    return time.fromisoformat(value) if value else None


# --- restaurant rules ---


def get_tables(conn: sqlite3.Connection) -> list[Table]:
    rows = conn.execute("SELECT id, capacity, zone FROM dining_tables").fetchall()
    return [Table(r["id"], r["capacity"], r["zone"]) for r in rows]


def get_opening_hours(conn: sqlite3.Connection, weekday: int) -> OpeningHours | None:
    r = conn.execute("SELECT * FROM opening_hours WHERE weekday = ?", (weekday,)).fetchone()
    if r is None:
        return None
    return OpeningHours(
        r["weekday"], _time(r["open_time"]), _time(r["last_seating"]), _time(r["close_time"])
    )


def get_closure_reason(conn: sqlite3.Connection, day: date) -> str | None:
    r = conn.execute(
        "SELECT reason FROM special_closures WHERE date = ?", (day.isoformat(),)
    ).fetchone()
    return r["reason"] if r else None


# --- slots, holds, reservations ---


def taken_slots(conn: sqlite3.Connection, start_key: str, end_key: str) -> set[tuple[str, str]]:
    rows = conn.execute(
        "SELECT table_id, slot_start FROM reservation_slots"
        " WHERE slot_start >= ? AND slot_start < ?",
        (start_key, end_key),
    ).fetchall()
    return {(r["table_id"], r["slot_start"]) for r in rows}


def insert_slots(
    conn: sqlite3.Connection,
    table_id: str,
    slot_keys: list[str],
    *,
    reservation_id: int | None = None,
    hold_id: str | None = None,
) -> None:
    conn.executemany(
        "INSERT INTO reservation_slots (table_id, slot_start, reservation_id, hold_id)"
        " VALUES (?, ?, ?, ?)",
        [(table_id, key, reservation_id, hold_id) for key in slot_keys],
    )


def _hold(r: sqlite3.Row) -> Hold:
    return Hold(
        r["id"],
        r["table_id"],
        date.fromisoformat(r["date"]),
        time.fromisoformat(r["start_time"]),
        r["party_size"],
        r["conversation_id"],
        r["expires_at"],
        r["status"],
    )


def insert_hold(conn: sqlite3.Connection, hold: Hold) -> None:
    conn.execute(
        "INSERT INTO holds (id, table_id, date, start_time, party_size, conversation_id,"
        " expires_at, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            hold.id,
            hold.table_id,
            hold.date.isoformat(),
            hold.start_time.strftime("%H:%M"),
            hold.party_size,
            hold.conversation_id,
            hold.expires_at,
            hold.status,
        ),
    )


def get_hold(conn: sqlite3.Connection, hold_id: str) -> Hold | None:
    r = conn.execute("SELECT * FROM holds WHERE id = ?", (hold_id,)).fetchone()
    return _hold(r) if r else None


def get_active_holds(conn: sqlite3.Connection) -> list[Hold]:
    rows = conn.execute("SELECT * FROM holds WHERE status = 'ACTIVE'").fetchall()
    return [_hold(r) for r in rows]


def close_hold(conn: sqlite3.Connection, hold_id: str, status: str) -> None:
    """Set a final status and free the hold's slots."""
    conn.execute("UPDATE holds SET status = ? WHERE id = ?", (status, hold_id))
    conn.execute("DELETE FROM reservation_slots WHERE hold_id = ?", (hold_id,))


def reservation_code_exists(conn: sqlite3.Connection, code: str) -> bool:
    return conn.execute("SELECT 1 FROM reservations WHERE code = ?", (code,)).fetchone() is not None


def insert_reservation(conn: sqlite3.Connection, res: NewReservation) -> int:
    cur = conn.execute(
        "INSERT INTO reservations (code, customer_name, phone, party_size, date, start_time,"
        " duration_min, table_id, notes, status, source, created_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'CONFIRMED', ?, ?)",
        (
            res.code,
            res.customer_name,
            res.phone,
            res.party_size,
            res.date.isoformat(),
            res.start_time.strftime("%H:%M"),
            res.duration_min,
            res.table_id,
            res.notes,
            res.source,
            res.created_at,
        ),
    )
    assert cur.lastrowid is not None
    return cur.lastrowid


# --- menu and allergens ---


def _menu_item(r: sqlite3.Row) -> MenuItem:
    return MenuItem(
        r["id"],
        r["name"],
        r["category"],
        r["description"],
        r["price_pln"],
        bool(r["is_available"]),
        tuple(json.loads(r["aliases"])),
    )


def get_menu_items(conn: sqlite3.Connection) -> list[MenuItem]:
    return [_menu_item(r) for r in conn.execute("SELECT * FROM menu_items").fetchall()]


def get_menu_item(conn: sqlite3.Connection, item_id: str) -> MenuItem | None:
    r = conn.execute("SELECT * FROM menu_items WHERE id = ?", (item_id,)).fetchone()
    return _menu_item(r) if r else None


def get_item_allergen_statuses(conn: sqlite3.Connection, item_id: str) -> dict[str, str]:
    rows = conn.execute(
        "SELECT allergen_code, status FROM menu_item_allergens WHERE item_id = ?", (item_id,)
    ).fetchall()
    return {r["allergen_code"]: r["status"] for r in rows}


def get_item_ingredients(conn: sqlite3.Connection, item_id: str) -> list[Ingredient]:
    rows = conn.execute(
        "SELECT i.* FROM ingredients i"
        " JOIN menu_item_ingredients mi ON mi.ingredient_id = i.id"
        " WHERE mi.item_id = ? ORDER BY i.id",
        (item_id,),
    ).fetchall()
    return [
        Ingredient(r["id"], r["name"], r["related_allergen_code"], r["related_note"]) for r in rows
    ]
