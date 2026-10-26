from decimal import Decimal

import pytest

from app.domain.nutrition_calc import (
    ItemInput,
    PortionError,
    compute_item,
    compute_totals,
    range_portion,
    servings_portion,
    weight_portion,
)

APPLE = {"energy_kcal": 52.0, "protein_g": 0.26, "carbs_g": 13.8, "fat_g": 0.17}


def test_weight_scales_per_100g() -> None:
    r = compute_item(ItemInput("apple", APPLE, weight_portion(150, "g")))
    assert r.nutrients["energy_kcal"] == (Decimal("78.0"), Decimal("78.0"))
    assert r.nutrients["carbs_g"][0] == Decimal("20.7")
    assert r.warnings == ()
    assert not r.uncertain


@pytest.mark.parametrize(
    ("amount", "unit", "grams"),
    [(1, "kg", "1000"), (2, "oz", "56.699"), (1, "lb", "453.592"), (250, "g", "250")],
)
def test_unit_conversion(amount: float, unit: str, grams: str) -> None:
    p = weight_portion(amount, unit)
    assert p.grams_low == p.grams_high
    assert abs(p.grams_low - Decimal(grams)) < Decimal("0.01")


@pytest.mark.parametrize("unit", ["cup", "ml", "tbsp", "slice", "piece"])
def test_volume_and_count_units_are_rejected(unit: str) -> None:
    with pytest.raises(PortionError):
        weight_portion(1, unit)


@pytest.mark.parametrize("amount", [0, -5, 0.01, 6000])
def test_out_of_range_weights_rejected(amount: float) -> None:
    with pytest.raises(PortionError):
        weight_portion(amount, "g")


def test_range_gives_low_high_and_flags_uncertain() -> None:
    r = compute_item(ItemInput("rice", {"energy_kcal": 130.0}, range_portion(100, 200, "g")))
    assert r.nutrients["energy_kcal"] == (Decimal("130.0"), Decimal("260.0"))
    assert r.uncertain and "portion_is_estimate" in r.warnings


def test_range_must_be_ordered() -> None:
    with pytest.raises(PortionError):
        range_portion(200, 100, "g")
    with pytest.raises(PortionError):
        range_portion(100, 100, "g")


def test_servings_need_a_source_serving_weight() -> None:
    assert servings_portion(2, 30).grams_low == Decimal("60")
    with pytest.raises(PortionError):
        servings_portion(2, None)
    with pytest.raises(PortionError):
        servings_portion(2, 0)


def test_missing_nutrient_is_absent_not_zero() -> None:
    r = compute_item(ItemInput("x", {"energy_kcal": 100.0}, weight_portion(100, "g")))
    assert "protein_g" not in r.nutrients
    assert "protein_g" in r.not_reported
    assert "partial_nutrients" in r.warnings


def test_zero_reported_by_source_is_kept_as_zero() -> None:
    r = compute_item(ItemInput("x", {**APPLE, "fat_g": 0.0}, weight_portion(100, "g")))
    assert r.nutrients["fat_g"] == (Decimal("0.0"), Decimal("0.0"))


def test_no_source_or_no_portion_gives_no_numbers() -> None:
    nosrc = compute_item(ItemInput("mystery", None, weight_portion(100, "g")))
    assert nosrc.nutrients == {} and "no_nutrition_data" in nosrc.warnings
    noport = compute_item(ItemInput("apple", APPLE, None))
    assert noport.nutrients == {} and "portion_missing" in noport.warnings


def test_totals_sum_and_flag_incomplete() -> None:
    a = compute_item(ItemInput("a", APPLE, weight_portion(100, "g")))
    b = compute_item(ItemInput("b", {"protein_g": 10.0}, weight_portion(100, "g")))
    c = compute_item(ItemInput("unknown", None, weight_portion(100, "g")))
    t = compute_totals([a, b, c])
    assert t["energy_kcal"].low == Decimal("52.0")
    assert not t["energy_kcal"].complete
    assert set(t["energy_kcal"].missing_items) == {"b", "unknown"}
    assert t["protein_g"].low == Decimal("10.26")
    assert t["fiber_g"].low is None  # nobody reported it: not 0


def test_totals_complete_when_all_items_contribute() -> None:
    a = compute_item(ItemInput("a", APPLE, weight_portion(100, "g")))
    b = compute_item(ItemInput("b", APPLE, range_portion(100, 200, "g")))
    t = compute_totals([a, b])["energy_kcal"]
    assert t.complete and (t.low, t.high) == (Decimal("104.0"), Decimal("156.0"))


def test_empty_meal_is_never_complete() -> None:
    assert not compute_totals([])["energy_kcal"].complete


def test_decimal_math_has_no_float_drift() -> None:
    r = compute_item(ItemInput("x", {"energy_kcal": 0.1}, weight_portion(300, "g")))
    assert r.nutrients["energy_kcal"][0] == Decimal("0.3")
