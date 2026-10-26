import pytest

from voice_agent.domain.allergens import lookup_allergens, resolve_allergen
from voice_agent.domain.errors import DomainError, ErrorCode


def one(db, item_id: str, asked: str):
    (result,) = lookup_allergens(db, item_id, [asked]).results
    return result


@pytest.mark.parametrize(
    ("term", "code"),
    [
        ("Tree Nuts", "nuts"),
        ("almonds", "nuts"),
        ("peanuts", "peanuts"),
        ("groundnuts", "peanuts"),
        ("dairy", "milk"),
        ("lactose", "milk"),
        ("wheat", "gluten"),
        ("shrimp", "crustaceans"),
        ("squid", "molluscs"),
        ("egg", "eggs"),
        ("sulfites", "sulphites"),
        ("garlic", None),
        ("nightshades", None),
        ("pine nuts", None),
    ],
)
def test_synonyms(term: str, code: str | None) -> None:
    assert resolve_allergen(term) == code


def test_pesto_is_nut_free_but_mentions_pine_nuts(db) -> None:
    result = one(db, "pasta-pesto-genovese", "nuts")
    assert (result.code, result.status) == ("nuts", "FREE")
    assert [r.name for r in result.related_ingredients] == ["pine nuts"]
    assert result.related_ingredients[0].note


def test_asking_for_pine_nuts_returns_ingredient_not_category(db) -> None:
    result = one(db, "pasta-pesto-genovese", "pine nuts")
    assert result.code is None and result.status is None
    assert [r.name for r in result.related_ingredients] == ["pine nuts"]


def test_contains(db) -> None:
    assert one(db, "pasta-pesto-genovese", "dairy").status == "CONTAINS"


def test_may_contain(db) -> None:
    assert one(db, "tiramisu", "hazelnuts").status == "MAY_CONTAIN"


def test_peanuts_are_not_tree_nuts(db) -> None:
    assert one(db, "spiedini-satay", "peanuts").status == "CONTAINS"
    assert one(db, "spiedini-satay", "nuts").status == "FREE"


def test_item_without_records_is_unknown(db) -> None:
    lookup = lookup_allergens(db, "special-of-the-week", ["gluten", "nuts", "milk"])
    assert {r.status for r in lookup.results} == {"UNKNOWN"}


def test_missing_row_is_unknown_never_free(db) -> None:
    db.execute(
        "DELETE FROM menu_item_allergens WHERE item_id = ? AND allergen_code = ?",
        ("pasta-pesto-genovese", "nuts"),
    )
    assert one(db, "pasta-pesto-genovese", "nuts").status == "UNKNOWN"


def test_untracked_allergen_has_no_code(db) -> None:
    result = one(db, "pasta-pesto-genovese", "garlic")
    assert (result.code, result.status) == (None, None)


def test_unknown_item(db) -> None:
    with pytest.raises(DomainError) as exc:
        lookup_allergens(db, "pizza-hawaii", ["nuts"])
    assert exc.value.code == ErrorCode.ITEM_NOT_FOUND
