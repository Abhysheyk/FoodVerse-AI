"""Deterministic recipe arithmetic and structural checks. No AI, no I/O."""

from decimal import ROUND_HALF_UP, Decimal

from app.ai.cooking import IngredientIn, RecipeDraft
from app.domain.diet_rules import Conflict, allergens_present, check_recipe
from app.schemas.food import TotalOut

MAX_SERVINGS = 24
_CENT = Decimal("0.01")


class RecipeError(ValueError):
    """A recipe that cannot be used. The message is user-facing."""


def _round(value: Decimal) -> float:
    return float(value.quantize(_CENT, rounding=ROUND_HALF_UP))


def scale_ingredient(ingredient: IngredientIn, factor: Decimal) -> IngredientIn:
    if ingredient.quantity is None:
        return ingredient
    scaled = Decimal(str(ingredient.quantity)) * factor
    return ingredient.model_copy(update={"quantity": _round(scaled)})


def scale_recipe(recipe: RecipeDraft, servings: int) -> RecipeDraft:
    """Scale to a new serving count. Numeric quantities scale; free-text stays as written."""
    if not 1 <= servings <= MAX_SERVINGS:
        raise RecipeError(f"A recipe can serve between 1 and {MAX_SERVINGS} people.")
    if servings == recipe.servings:
        return recipe
    factor = Decimal(servings) / Decimal(recipe.servings)
    return recipe.model_copy(
        update={
            "servings": servings,
            "ingredients": [scale_ingredient(i, factor) for i in recipe.ingredients],
        }
    )


def enforce(
    recipe: RecipeDraft, allergies: list[str], diets: list[str]
) -> list[Conflict]:
    """The hard gate. A non-empty result means the recipe must not be stored or shown."""
    names = [i.name for i in recipe.ingredients]
    if not names:
        raise RecipeError("A recipe must have at least one ingredient.")
    return check_recipe(recipe.title, names, allergies, diets)


def allergy_disclosure(recipe: RecipeDraft, allergies: list[str]) -> dict[str, list[str]]:
    """What the app asserts independently of the model."""
    detected = allergens_present([i.name for i in recipe.ingredients])
    warnings = [
        "This ingredient list is a suggestion, not a label. Check every package and ask about "
        "cross-contact wherever the food was prepared or bought.",
    ]
    if detected:
        warnings.append("Allergens detected in the ingredients: " + ", ".join(detected) + ".")
    if allergies:
        warnings.append(
            "Your declared allergies were checked against the ingredient names: "
            + ", ".join(allergies)
            + "."
        )
    return {"detected_allergens": detected, "warnings": warnings}


def divide_totals(totals: dict[str, TotalOut], servings: int) -> dict[str, TotalOut]:
    """Per-serving figures from whole-recipe totals (deterministic, half-up to 2 dp)."""
    if servings < 1:
        raise RecipeError("Servings must be at least 1.")
    divisor = Decimal(servings)
    out: dict[str, TotalOut] = {}
    for key, total in totals.items():
        low = total.low if total.low is not None else None
        high = total.high if total.high is not None else None
        out[key] = total.model_copy(
            update={
                "low": _round(Decimal(str(low)) / divisor) if low is not None else None,
                "high": _round(Decimal(str(high)) / divisor) if high is not None else None,
            }
        )
    return out  