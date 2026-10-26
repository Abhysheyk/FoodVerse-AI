"""The nutrients FoodVerse reports. All source values are normalised to these keys and units,
always on a per-100 g basis. A nutrient a source does not supply is simply absent: it is never
defaulted to zero or estimated."""

from dataclasses import dataclass


@dataclass(frozen=True)
class NutrientDef:
    key: str
    label: str
    unit: str
    core: bool  # core nutrients are always shown (as "not available" when missing)
    max_per_100g: float  # sanity bound; larger values are treated as malformed source data


NUTRIENTS: tuple[NutrientDef, ...] = (
    NutrientDef("energy_kcal", "Calories", "kcal", True, 1000.0),
    NutrientDef("protein_g", "Protein", "g", True, 100.5),
    NutrientDef("carbs_g", "Carbohydrates", "g", True, 100.5),
    NutrientDef("fat_g", "Fat", "g", True, 100.5),
    NutrientDef("fiber_g", "Fibre", "g", False, 100.5),
    NutrientDef("sugars_g", "Sugars", "g", False, 100.5),
    NutrientDef("saturated_fat_g", "Saturated fat", "g", False, 100.5),
    NutrientDef("sodium_mg", "Sodium", "mg", False, 40_000.0),
)
NUTRIENT_BY_KEY: dict[str, NutrientDef] = {n.key: n for n in NUTRIENTS}
