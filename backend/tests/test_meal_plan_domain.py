"""Domain-level tests: constraint enforcement and grocery arithmetic. No DB, no HTTP."""

from app.domain.grocery import merge_ingredients
from app.domain.meal_plan import Constraints, find_violations, soft_warnings


def _days(*ingredient_names: str, meal="lunch", title="Test meal") -> list[dict]:
    return [
        {
            "day_date": "2026-11-02",
            "meals": [
                {
                    "meal": meal,
                    "title": title,
                    "servings": 1,
                    "cooking_minutes": 15,
                    "ingredients": [
                        {"name": n, "quantity": 100, "unit": "g"} for n in ingredient_names
                    ],
                }
            ],
        }
    ]


# ---- constraint enforcement ----
def test_allergy_keyword_match_is_rejected():
    v = find_violations(
        days=_days("peanut butter"),
        constraints=Constraints("omnivore", ("peanut",), ()),
    )
    assert v and v[0].code == "allergy:peanut" and v[0].ingredient == "peanut butter"


def test_allergy_synonyms_match_tree_nut_family():
    v = find_violations(
        days=_days("almond milk"),
        constraints=Constraints("omnivore", ("tree nut",), ()),
    )
    assert v and v[0].code == "allergy:tree nut"


def test_allergy_match_is_plural_tolerant():
    v = find_violations(
        days=_days("2 onions, diced", "peanuts roasted"),
        constraints=Constraints("omnivore", ("peanut",), ()),
    )
    assert v and "peanut" in v[0].code


def test_excluded_ingredient_is_rejected_exactly():
    v = find_violations(
        days=_days("fresh garlic"),
        constraints=Constraints("omnivore", (), ("garlic",)),
    )
    assert v and v[0].code == "excluded:garlic"


def test_vegan_forbids_animal_products():
    v = find_violations(
        days=_days("butter", "chicken stock", "honey"),
        constraints=Constraints("vegan", (), ()),
    )
    codes = sorted({x.code for x in v})
    assert "diet:vegan" in codes and len(v) == 3


def test_jain_forbids_root_vegetables():
    v = find_violations(
        days=_days("onion", "potato"),
        constraints=Constraints("jain", (), ()),
    )
    assert len(v) == 2 and all(x.code == "diet:jain" for x in v)


def test_omnivore_with_no_constraints_never_rejects():
    assert not find_violations(
        days=_days("chicken", "butter", "garlic", "onion"),
        constraints=Constraints("omnivore", (), ()),
    )


def test_all_constraint_violations_are_listed_not_truncated():
    v = find_violations(
        days=_days("peanut", "milk", "egg"),
        constraints=Constraints("omnivore", ("peanut", "milk", "egg"), ()),
    )
    assert len(v) == 3


def test_cooking_time_overrun_is_only_a_soft_warning():
    days = _days("rice")
    days[0]["meals"][0]["cooking_minutes"] = 90
    w = soft_warnings(days=days, max_cooking_minutes=30)
    assert w.cooking_time and w.cooking_time[0]["cooking_minutes"] == 90


# ---- grocery merging ----
def test_grocery_merges_same_mass_across_units():
    merged = merge_ingredients(
        [("rice", 500, "g"), ("Rice", 1, "kg"), ("rice", 2, "oz")]
    )
    assert len(merged) == 1
    assert merged[0]["name"].lower() == "rice"
    assert merged[0]["unit"] == "kg"
    assert abs(merged[0]["quantity"] - 1.5567) < 0.01  # 500 + 1000 + 56.7


def test_grocery_never_merges_across_families():
    merged = merge_ingredients([("salt", 100, "g"), ("salt", 2, "tsp")])
    names = sorted((m["name"], m["unit"]) for m in merged)
    assert names == [("salt", "g"), ("salt", "tsp")]


def test_grocery_never_merges_volume_with_mass():
    merged = merge_ingredients([("milk", 500, "ml"), ("milk", 200, "g")])
    assert len(merged) == 2


def test_grocery_never_merges_different_names():
    merged = merge_ingredients([("garlic", 5, "g"), ("garlic powder", 5, "g")])
    assert len(merged) == 2


def test_grocery_count_units_only_merge_when_identical():
    assert len(merge_ingredients([("egg", 2, "piece"), ("egg", 3, "piece")])) == 1
    assert len(merge_ingredients([("egg", 2, "piece"), ("egg", 2, "slice")])) == 2


def test_grocery_zero_and_blank_quantities_are_skipped():
    merged = merge_ingredients([("ghost", 0, "g"), ("", 100, "g")])
    assert merged == []