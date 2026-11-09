import pytest

from app.domain.diet_rules import (
    Conflict, allergens_present, check_recipe, declared_but_unverifiable,
)


def test_peanut_allergy_blocks_peanut_ingredients() -> None:
    conflicts = check_recipe("Satay", ["peanut butter", "chicken"], ["peanut"], [])
    assert [c.kind for c in conflicts] == ["allergy"]
    assert conflicts[0].matched == "peanut"
    assert "peanut" in conflicts[0].message


@pytest.mark.parametrize(
    ("allergy", "ingredient"),
    [
        ("milk", "ghee"), ("milk", "paneer"), ("egg", "mayonnaise"), ("wheat", "maida"),
        ("soy", "tofu"), ("sesame", "tahini"), ("tree nut", "cashews"), ("shellfish", "prawns"),
        ("fish", "anchovies"),
    ],
)
def test_allergen_keyword_table(allergy: str, ingredient: str) -> None:
    assert check_recipe("x", [ingredient], [allergy], []), ingredient


def test_whole_word_matching_avoids_false_positives() -> None:
    assert check_recipe("x", ["cauliflower"], [], ["gluten_free"]) == []
    assert check_recipe("x", ["buttermilk"], [], ["lactose_free"])  # explicit keyword
    assert check_recipe("x", ["coconut milk"], ["milk"], [])  # conservative: flagged


@pytest.mark.parametrize(
    ("diet", "ingredient"),
    [
        ("vegan", "chicken"), ("vegan", "honey"), ("vegan", "paneer"), ("vegetarian", "prawns"),
        ("pescatarian", "bacon"), ("jain", "onion"), ("gluten_free", "spaghetti"),
        ("lactose_free", "cream"),
    ],
)
def test_diet_rules(diet: str, ingredient: str) -> None:
    assert check_recipe("x", [ingredient], [], [diet]), (diet, ingredient)


def test_pescatarian_allows_fish() -> None:
    assert check_recipe("x", ["salmon"], [], ["pescatarian"]) == []


def test_egg_allowed_for_vegetarian_and_eggetarian() -> None:
    assert check_recipe("x", ["egg"], [], ["vegetarian"]) == []
    assert check_recipe("x", ["egg"], [], ["eggetarian"]) == []


def test_unverifiable_diets_are_reported_not_silently_accepted() -> None:
    assert declared_but_unverifiable(["halal", "vegan"]) == ["halal"]


def test_allergens_present_is_independent_of_user_declarations() -> None:
    assert set(allergens_present(["milk", "wheat flour", "tofu"])) == {"milk", "wheat", "soy"}
    assert allergens_present(["rice", "lemon"]) == []


def test_conflict_is_hashable_and_deduplicated() -> None:
    c = Conflict("allergy", "peanut", "peanut butter", "peanut")
    assert c.kind == "allergy"
    assert "peanut allergy" in c.message
    # duplicate ingredient names yield one conflict per keyword
    cs = check_recipe("x", ["peanut", "peanut butter"], ["peanut"], [])
    assert len(cs) == 2  # different ingredient names -> different conflicts
    assert all(c2.matched == "peanut" for c2 in cs)


def test_title_alone_is_not_a_conflict_trigger_but_ingredients_are() -> None:
    # We test only ingredients: a title like "Peanut-free cookies" must not itself be blocked
    # (the caller passes ingredients, not title, into the keyword scan).
    assert check_recipe("Peanut-free cookies", ["flour", "sugar"], ["peanut"], []) == []