from voice_agent.domain.menu import search_menu


def test_unique_name_is_exact(db) -> None:
    result = search_menu(db, "pesto genovese")
    assert result.match == "exact"
    assert [c.item_id for c in result.candidates] == ["pasta-pesto-genovese"]


def test_alias_is_exact(db) -> None:
    result = search_menu(db, "carbonara")
    assert result.match == "exact"
    assert result.candidates[0].item_id == "spaghetti-carbonara"


def test_similar_names_are_ambiguous(db) -> None:
    result = search_menu(db, "pesto")
    assert result.match == "ambiguous"
    ids = [c.item_id for c in result.candidates]
    assert {"pasta-pesto-genovese", "pesto-rosso"} <= set(ids)
    assert len(ids) <= 3


def test_sold_out_item_is_flagged(db) -> None:
    result = search_menu(db, "sea bass")
    assert result.candidates[0].item_id == "branzino-al-forno"
    assert result.candidates[0].sold_out


def test_category_filter(db) -> None:
    result = search_menu(db, "pesto", category="dessert")
    assert all(c.category == "dessert" for c in result.candidates)
