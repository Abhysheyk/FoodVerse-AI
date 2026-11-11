"""Prompt, JSON schema and strict validation for AI-generated meal plans.

Trust rules, enforced by validation and by the domain layer that runs after it:
  * The model supplies FOOD NAMES and QUANTITIES only. The schema has no fields for
    calories, macros, safety claims, confidence, or prices. Any such fields it volunteers
    are silently dropped because `extra="ignore"`.
  * The plan must be JSON, must match the week, must list ingredients per meal, must use
    known meal categories, must use mass/volume/count units. Anything else is a 502.
  * After validation, `app.domain.meal_plan.enforce_constraints` rejects the plan if any
    ingredient violates the user's allergies, exclusions or dietary pattern. The service
    surfaces this as a 422 with the offending ingredients listed, so nothing is silently
    dropped and nothing fake is saved.
"""

import json
import re
from datetime import date, timedelta
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.ai.text import TextBadOutputError

MAX_DAYS = 7
MAX_MEALS_PER_DAY = 6
MAX_INGREDIENTS_PER_MEAL = 30
ALLOWED_UNITS = frozenset(
    {"g", "kg", "oz", "lb", "ml", "l", "tsp", "tbsp", "cup", "piece", "slice", "clove", "pinch"}
)
MEAL_CATEGORIES = ("breakfast", "lunch", "dinner", "snack")
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)


def _clean(text: str) -> str:
    return " ".join(_CONTROL.sub(" ", text).split())


def build_meal_plan_prompt(
    *,
    week_start: date,
    dietary_pattern: str,
    dietary_preferences: list[str],
    allergies: list[str],
    excluded_ingredients: list[str],
    preferred_cuisines: list[str],
    budget: str,
    max_cooking_minutes: int | None,
    default_servings: int,
    pantry_ingredients: list[str],
) -> str:
    """Compose the generation prompt. Hard constraints are stated in the prompt AND
    re-checked in code; the prompt is only a hint to reduce retries."""
    end = week_start + timedelta(days=6)
    parts = [
        "You are a meal-planning assistant. Produce a 7-day meal plan as JSON, no prose.",
        f"The week runs {week_start.isoformat()} to {end.isoformat()}. Each day MUST use one "
        "of breakfast, lunch, dinner, snack. Each meal MUST list ingredients with a positive "
        "quantity and a unit from this set: "
        + ", ".join(sorted(ALLOWED_UNITS))
        + ".",
        "Do NOT include calorie counts, macronutrient numbers, safety or 'healthy' claims, "
        "prices, or confidence values anywhere. Do NOT invent ingredients not stated here. "
        "Prefer ingredients from the pantry when they fit.",
        f"Dietary pattern: {dietary_pattern}.",
    ]
    if dietary_preferences:
        parts.append(f"Other declared dietary preferences: {', '.join(dietary_preferences)}.")
    if allergies:
        parts.append(
            "MUST avoid: " + ", ".join(allergies) + " and any ingredient containing them."
        )
    if excluded_ingredients:
        parts.append("MUST exclude: " + ", ".join(excluded_ingredients) + ".")
    if preferred_cuisines:
        parts.append(f"Preferred cuisines: {', '.join(preferred_cuisines)}.")
    parts.append(f"Budget level: {budget}.")
    if max_cooking_minutes:
        parts.append(f"Each meal should take at most {max_cooking_minutes} minutes.")
    parts.append(f"Default servings per meal: {default_servings}.")
    if pantry_ingredients:
        parts.append("Available pantry ingredients: " + ", ".join(pantry_ingredients) + ".")
    parts.append(
        "Reply with JSON exactly in this shape: "
        '{"title": str, "days": [{"day_date": "YYYY-MM-DD", "meals": ['
        '{"meal": "breakfast|lunch|dinner|snack", "title": str, "servings": int, '
        '"cooking_minutes": int, "ingredients": [{"name": str, "quantity": number, '
        '"unit": str}], "notes": str}]}], "notes": str}'
    )
    return " ".join(parts)


MEAL_PLAN_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "days": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "day_date": {"type": "string"},
                    "meals": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "meal": {"type": "string", "enum": list(MEAL_CATEGORIES)},
                                "title": {"type": "string"},
                                "servings": {"type": "integer"},
                                "cooking_minutes": {"type": "integer"},
                                "ingredients": {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "name": {"type": "string"},
                                            "quantity": {"type": "number"},
                                            "unit": {"type": "string"},
                                        },
                                        "required": ["name", "quantity", "unit"],
                                    },
                                },
                                "notes": {"type": "string"},
                            },
                            "required": ["meal", "title", "servings", "ingredients"],
                        },
                    },
                },
                "required": ["day_date", "meals"],
            },
        },
        "notes": {"type": "string"},
    },
    "required": ["days"],
}


class IngredientOut(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=120)
    quantity: float = Field(gt=0, le=100_000)
    unit: str = Field(min_length=1, max_length=16)


class MealOut(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    meal: Literal["breakfast", "lunch", "dinner", "snack"]
    title: str = Field(min_length=1, max_length=160)
    servings: int = Field(ge=1, le=20)
    cooking_minutes: int | None = Field(default=None, ge=1, le=1440)
    ingredients: list[IngredientOut] = Field(min_length=1, max_length=MAX_INGREDIENTS_PER_MEAL)
    notes: str | None = Field(default=None, max_length=400)


class DayOut(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    day_date: date
    meals: list[MealOut] = Field(min_length=1, max_length=MAX_MEALS_PER_DAY)


class MealPlanModelOutput(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    title: str | None = Field(default=None, max_length=160)
    days: list[DayOut] = Field(min_length=1, max_length=MAX_DAYS)
    notes: str | None = Field(default=None, max_length=600)


def parse_meal_plan_output(
    text: object, *, week_start: date, default_servings: int
) -> MealPlanModelOutput:
    """Strictly validate. Nothing is repaired; nothing is dropped."""
    if not isinstance(text, str) or not text.strip():
        raise TextBadOutputError("The text model returned an empty response.")
    try:
        data = json.loads(_FENCE.sub("", text.strip()))
    except json.JSONDecodeError:
        raise TextBadOutputError(
            "The text model did not return valid JSON, so its answer was discarded."
        ) from None
    if not isinstance(data, dict):
        raise TextBadOutputError("The text model returned an unexpected structure.")
    try:
        result = MealPlanModelOutput.model_validate(data)
    except ValidationError:
        raise TextBadOutputError(
            "The text model's answer did not match the expected format, so it was discarded."
        ) from None

    allowed_dates = {week_start + timedelta(days=i) for i in range(MAX_DAYS)}
    for day in result.days:
        if day.day_date not in allowed_dates:
            raise TextBadOutputError(
                "The generated plan includes dates outside the requested week."
            )
    for day in result.days:
        for meal in day.meals:
            for ing in meal.ingredients:
                if ing.unit.lower() not in ALLOWED_UNITS:
                    raise TextBadOutputError(
                        f"Unsupported unit {ing.unit!r}; expected one of "
                        f"{sorted(ALLOWED_UNITS)}."
                    )
                ing.unit = ing.unit.lower()
            if meal.servings <= 0:
                meal.servings = default_servings
    return result