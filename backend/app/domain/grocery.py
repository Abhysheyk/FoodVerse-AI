"""Deterministic grocery-list merging.

Rules — deliberately conservative, no ingredient ontology:
  * Merge only items with the same normalised name AND a compatible unit family.
  * Mass family: {g, kg, oz, lb}, base unit grams.
  * Volume family: {ml, l, tsp, tbsp, cup}, base unit millilitres.
  * Count family: only identical units merge (piece+piece, slice+slice).
  * Anything else stays as its own line item.
Equivalent ingredients with different names are NEVER merged.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

MASS_TO_G: dict[str, Decimal] = {
    "g": Decimal("1"),
    "kg": Decimal("1000"),
    "oz": Decimal("28.349523125"),
    "lb": Decimal("453.59237"),
}
VOLUME_TO_ML: dict[str, Decimal] = {
    "ml": Decimal("1"),
    "l": Decimal("1000"),
    "tsp": Decimal("4.92892159375"),
    "tbsp": Decimal("14.78676478125"),
    "cup": Decimal("236.5882365"),
}
COUNT_UNITS = frozenset({"piece", "slice", "clove", "pinch"})
_COUNT = Decimal("0.01")


def _family(unit: str) -> str:
    u = unit.lower().strip()
    if u in MASS_TO_G:
        return "mass"
    if u in VOLUME_TO_ML:
        return "volume"
    if u in COUNT_UNITS:
        return f"count:{u}"
    return f"other:{u}"


def _to_base(quantity: Decimal, unit: str) -> Decimal:
    u = unit.lower().strip()
    if u in MASS_TO_G:
        return quantity * MASS_TO_G[u]
    if u in VOLUME_TO_ML:
        return quantity * VOLUME_TO_ML[u]
    return quantity


def _preferred_unit(family: str, base_total: Decimal) -> tuple[Decimal, str]:
    """Choose a natural display unit within the family (never crosses families)."""
    if family == "mass":
        return (base_total / 1000, "kg") if base_total >= 1000 else (base_total, "g")
    if family == "volume":
        return (base_total / 1000, "l") if base_total >= 1000 else (base_total, "ml")
    return base_total, family.split(":", 1)[1]


def _qty(value: Decimal) -> float:
    return float(value.quantize(_COUNT, rounding=ROUND_HALF_UP))


@dataclass
class _Bucket:
    name: str
    family: str
    base_total: Decimal
    original_unit: str


def merge_ingredients(
    lines: list[tuple[str, float, str]]
) -> list[dict[str, object]]:
    """Merge (name, quantity, unit) triples into grocery-list rows.

    The returned dicts are the shape stored in `grocery_items`.
    """
    buckets: dict[tuple[str, str], _Bucket] = {}
    for raw_name, quantity, raw_unit in lines:
        name = " ".join(raw_name.split())
        if not name or quantity <= 0:
            continue
        unit = raw_unit.lower().strip()
        key = (name.casefold(), _family(unit))
        bucket = buckets.get(key)
        base = _to_base(Decimal(str(quantity)), unit)
        if bucket is None:
            buckets[key] = _Bucket(name=name, family=key[1], base_total=base, original_unit=unit)
        else:
            bucket.base_total += base

    out: list[dict[str, object]] = []
    for bucket in buckets.values():
        display_total, unit = _preferred_unit(bucket.family, bucket.base_total)
        out.append(
            {
                "name": bucket.name,
                "quantity": _qty(display_total),
                "unit": unit,
            }
        )
    out.sort(key=lambda row: (str(row["name"]).casefold(), str(row["unit"])))
    return out