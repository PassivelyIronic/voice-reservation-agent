"""Allergen lookup. The only source of truth is menu_item_allergens; a missing row is UNKNOWN."""

import sqlite3
from dataclasses import dataclass
from typing import Literal

from voice_agent.db import repository as repo
from voice_agent.domain.errors import DomainError, ErrorCode

AllergenStatus = Literal["CONTAINS", "MAY_CONTAIN", "FREE", "UNKNOWN"]

# What callers say -> EU-14 code (docs/plan/04-data-model.md).
_SYNONYMS: dict[str, tuple[str, ...]] = {
    "gluten": ("gluten", "wheat", "flour"),
    "crustaceans": (
        "crustaceans",
        "crustacean",
        "shellfish",
        "shrimp",
        "shrimps",
        "prawn",
        "prawns",
        "crab",
        "crabs",
        "lobster",
        "lobsters",
    ),
    "eggs": ("egg", "eggs"),
    "fish": ("fish",),
    "peanuts": ("peanut", "peanuts", "groundnut", "groundnuts"),
    "soy": ("soy", "soya", "soybean", "soybeans"),
    "milk": ("milk", "dairy", "lactose", "cheese"),
    "nuts": (
        "nuts",
        "nut",
        "tree nuts",
        "tree nut",
        "walnut",
        "walnuts",
        "almond",
        "almonds",
        "hazelnut",
        "hazelnuts",
        "cashew",
        "cashews",
        "pistachio",
        "pistachios",
        "pecan",
        "pecans",
        "brazil nuts",
        "macadamia",
        "macadamias",
    ),
    "celery": ("celery", "celeriac"),
    "mustard": ("mustard",),
    "sesame": ("sesame", "sesame seeds"),
    "sulphites": ("sulphites", "sulfites", "sulphite", "sulfite", "sulphur dioxide"),
    "lupin": ("lupin", "lupine"),
    "molluscs": (
        "molluscs",
        "mollusks",
        "mollusc",
        "mollusk",
        "mussels",
        "clams",
        "squid",
        "octopus",
        "oysters",
        "scallops",
    ),
}
SYNONYMS: dict[str, str] = {term: code for code, terms in _SYNONYMS.items() for term in terms}


@dataclass(frozen=True)
class RelatedIngredient:
    name: str
    note: str | None


@dataclass(frozen=True)
class AllergenResult:
    asked: str
    code: str | None  # None: not one of the 14 tracked allergens
    status: AllergenStatus | None  # None when code is None
    related_ingredients: tuple[RelatedIngredient, ...]


@dataclass(frozen=True)
class AllergenLookup:
    item_id: str
    item_name: str
    results: tuple[AllergenResult, ...]


def _normalize(term: str) -> str:
    return " ".join(term.lower().replace("-", " ").split())


def resolve_allergen(term: str) -> str | None:
    return SYNONYMS.get(_normalize(term))


def _status(raw: str | None) -> AllergenStatus:
    if raw == "CONTAINS":
        return "CONTAINS"
    if raw == "MAY_CONTAIN":
        return "MAY_CONTAIN"
    if raw == "FREE":
        return "FREE"
    return "UNKNOWN"


def lookup_allergens(conn: sqlite3.Connection, item_id: str, asked: list[str]) -> AllergenLookup:
    item = repo.get_menu_item(conn, item_id)
    if item is None:
        raise DomainError(ErrorCode.ITEM_NOT_FOUND, f"No menu item {item_id}.")
    statuses = repo.get_item_allergen_statuses(conn, item_id)
    ingredients = repo.get_item_ingredients(conn, item_id)
    results: list[AllergenResult] = []
    for term in asked:
        code = resolve_allergen(term)
        related = tuple(
            RelatedIngredient(i.name, i.related_note)
            for i in ingredients
            if (code is not None and i.related_allergen_code == code)
            # By name only for ingredients with an approved customer note (e.g. pine nuts):
            # "It does contain garlic." would be an unverified claim.
            or (i.related_note is not None and _normalize(term) == _normalize(i.name))
        )
        status = _status(statuses.get(code)) if code is not None else None
        results.append(AllergenResult(term, code, status, related))
    return AllergenLookup(item.id, item.name, tuple(results))
