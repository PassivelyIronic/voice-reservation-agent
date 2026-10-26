"""Fuzzy menu search over item names and aliases."""

import sqlite3
from dataclasses import dataclass
from typing import Literal

from rapidfuzz import fuzz, utils

from voice_agent.db import repository as repo
from voice_agent.domain.policy import MENU_EXACT_MARGIN, MENU_EXACT_SCORE, MENU_MAX_CANDIDATES


@dataclass(frozen=True)
class MenuMatch:
    item_id: str
    name: str
    category: str
    score: float
    sold_out: bool


@dataclass(frozen=True)
class MenuSearchResult:
    match: Literal["exact", "ambiguous"]
    candidates: tuple[MenuMatch, ...]


def _score(query: str, item: repo.MenuItem) -> float:
    return max(
        fuzz.WRatio(query, text, processor=utils.default_process)
        for text in (item.name, *item.aliases)
    )


def search_menu(conn: sqlite3.Connection, query: str, category: str = "any") -> MenuSearchResult:
    """`exact` if the best score >= 85 and leads the runner-up by >= 10, else <= 3 candidates."""
    items = [i for i in repo.get_menu_items(conn) if category in ("any", i.category)]
    ranked = sorted(
        (MenuMatch(i.id, i.name, i.category, _score(query, i), not i.is_available) for i in items),
        key=lambda m: (-m.score, m.item_id),
    )
    if ranked and ranked[0].score >= MENU_EXACT_SCORE:
        runner_up = ranked[1].score if len(ranked) > 1 else 0.0
        if ranked[0].score - runner_up >= MENU_EXACT_MARGIN:
            return MenuSearchResult("exact", (ranked[0],))
    return MenuSearchResult("ambiguous", tuple(ranked[:MENU_MAX_CANDIDATES]))
