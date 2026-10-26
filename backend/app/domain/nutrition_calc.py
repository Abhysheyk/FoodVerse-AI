"""Deterministic nutrition arithmetic. No I/O, no AI, no estimation.

    nutrient amount = (nutrient per 100 g) x (grams eaten) / 100

Everything is computed with Decimal and rounded only once, at the output boundary (2 dp,
half-up). A total is the sum of the *unrounded* item amounts, so displayed item figures may differ
from the displayed total by a rounding hair, never more.

What this module refuses to do, by design:
  * infer a weight from a photo or a food name (a portion must be supplied by the user);
  * convert volume to weight (that needs a density nobody has verified);
  * treat a nutrient the source did not report as zero.

A portion given as a range yields a low and a high figure, and is flagged uncertain.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from app.nutrition.nutrients import NUTRIENTS

MASS_TO_GRAMS: dict[str, Decimal] = {
    "g": Decimal("1"),
    "kg": Decimal("1000"),
    "oz": Decimal("28.349523125"),  # international avoirdupois ounce
    "lb": Decimal("453.59237"),  # international avoirdupois pound
}
MIN_GRAMS = Decimal("0.1")
MAX_GRAMS = Decimal("5000")
_CENT = Decimal("0.01")


class PortionError(ValueError):
    """A portion that cannot be converted to grams safely. The message is user-facing."""


def to_decimal(value: float | int | str) -> Decimal:
    return Decimal(str(value))


def round_amount(value: Decimal) -> Decimal:
    return value.quantize(_CENT, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class Portion:
    grams_low: Decimal
    grams_high: Decimal
    uncertain: bool  # True when the user gave a range rather than a weight
    description: str


def _grams(amount: Decimal, unit: str) -> Decimal:
    factor = MASS_TO_GRAMS.get(unit)
    if factor is None:
        raise PortionError(
            f"'{unit}' cannot be converted to grams. Use g, kg, oz or lb. Volumes such as cups "
            "or millilitres depend on the food's density, so please enter a weight."
        )
    if amount <= 0:
        raise PortionError("A portion must be greater than zero.")
    grams = amount * factor
    if not MIN_GRAMS <= grams <= MAX_GRAMS:
        raise PortionError(
            f"A portion must be between {MIN_GRAMS} g and {MAX_GRAMS} g for a single food item."
        )
    return grams


def weight_portion(amount: float | str, unit: str) -> Portion:
    grams = _grams(to_decimal(amount), unit)
    return Portion(grams, grams, False, f"{to_decimal(amount).normalize():f} {unit}")


def range_portion(min_amount: float | str, max_amount: float | str, unit: str) -> Portion:
    low = _grams(to_decimal(min_amount), unit)
    high = _grams(to_decimal(max_amount), unit)
    if low >= high:
        raise PortionError("In a range, the minimum must be smaller than the maximum.")
    return Portion(
        low,
        high,
        True,
        f"{to_decimal(min_amount).normalize():f}-"
        f"{to_decimal(max_amount).normalize():f} {unit} (estimate)",
    )


def servings_portion(count: float | str, serving_grams: float | None) -> Portion:
    if serving_grams is None or serving_grams <= 0:
        raise PortionError(
            "This food's source does not give a serving size in grams. Please enter a weight."
        )
    grams = _grams(to_decimal(count) * to_decimal(serving_grams), "g")
    return Portion(
        grams,
        grams,
        False,
        f"{to_decimal(count).normalize():f} x {to_decimal(serving_grams).normalize():f} g serving",
    )


@dataclass(frozen=True)
class ItemInput:
    name: str
    per_100g: Mapping[str, float] | None  # None: no nutrition source was chosen for this item
    portion: Portion | None  # None: the user has not given a portion yet


@dataclass(frozen=True)
class ItemResult:
    name: str
    grams_low: Decimal | None
    grams_high: Decimal | None
    uncertain: bool
    has_nutrition_data: bool
    nutrients: dict[str, tuple[Decimal, Decimal]]  # key -> (low, high); only reported nutrients
    not_reported: tuple[str, ...]
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class TotalNutrient:
    key: str
    low: Decimal | None  # None: no item reported this nutrient
    high: Decimal | None
    complete: bool  # True only if every item contributed
    contributing_items: int
    missing_items: tuple[str, ...]


def compute_item(item: ItemInput) -> ItemResult:
    warnings: list[str] = []
    if item.per_100g is None:
        warnings.append("no_nutrition_data")
    if item.portion is None:
        warnings.append("portion_missing")
    elif item.portion.uncertain:
        warnings.append("portion_is_estimate")

    nutrients: dict[str, tuple[Decimal, Decimal]] = {}
    not_reported: tuple[str, ...] = ()
    if item.per_100g is not None:
        not_reported = tuple(n.key for n in NUTRIENTS if n.key not in item.per_100g)
        if any(n.core and n.key not in item.per_100g for n in NUTRIENTS):
            warnings.append("partial_nutrients")
        if item.portion is not None:
            for n in NUTRIENTS:
                if n.key in item.per_100g:
                    per_100g = to_decimal(item.per_100g[n.key])
                    nutrients[n.key] = (
                        per_100g * item.portion.grams_low / 100,
                        per_100g * item.portion.grams_high / 100,
                    )
    return ItemResult(
        name=item.name,
        grams_low=item.portion.grams_low if item.portion else None,
        grams_high=item.portion.grams_high if item.portion else None,
        uncertain=bool(item.portion and item.portion.uncertain),
        has_nutrition_data=item.per_100g is not None,
        nutrients=nutrients,
        not_reported=not_reported,
        warnings=tuple(warnings),
    )


def compute_totals(results: Sequence[ItemResult]) -> dict[str, TotalNutrient]:
    totals: dict[str, TotalNutrient] = {}
    for n in NUTRIENTS:
        contributing = [r for r in results if n.key in r.nutrients]
        missing = tuple(r.name for r in results if n.key not in r.nutrients)
        low = (
            sum((r.nutrients[n.key][0] for r in contributing), Decimal(0)) if contributing else None
        )
        high = (
            sum((r.nutrients[n.key][1] for r in contributing), Decimal(0)) if contributing else None
        )
        totals[n.key] = TotalNutrient(
            key=n.key,
            low=low,
            high=high,
            complete=bool(results) and not missing,
            contributing_items=len(contributing),
            missing_items=missing,
        )
    return totals
