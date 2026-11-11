import uuid
from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

MAX_PLAN_DAYS = 7
MAX_MEALS_PER_DAY = 6
MAX_INGREDIENTS_PER_MEAL = 30
ALLOWED_UNITS = frozenset(
    {"g", "kg", "oz", "lb", "ml", "l", "tsp", "tbsp", "cup", "piece", "slice", "clove", "pinch"}
)


class IngredientIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: Annotated[str, Field(min_length=1, max_length=120)]
    quantity: float = Field(gt=0, le=100_000)
    unit: str = Field(min_length=1, max_length=16)

    @field_validator("unit")
    @classmethod
    def _known_unit(cls, v: str) -> str:
        u = v.lower()
        if u not in ALLOWED_UNITS:
            raise ValueError(f"Unit must be one of {sorted(ALLOWED_UNITS)}.")
        return u


class MealIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    meal: Literal["breakfast", "lunch", "dinner", "snack"]
    title: Annotated[str, Field(min_length=1, max_length=160)]
    servings: int = Field(ge=1, le=20)
    cooking_minutes: int | None = Field(default=None, ge=1, le=1440)
    ingredients: list[IngredientIn] = Field(min_length=1, max_length=MAX_INGREDIENTS_PER_MEAL)
    notes: str | None = Field(default=None, max_length=400)


class DayIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    day_date: date
    meals: list[MealIn] = Field(min_length=1, max_length=MAX_MEALS_PER_DAY)


class PlanBody(BaseModel):
    """Full plan payload accepted from the client (create / update / copy target)."""

    model_config = ConfigDict(extra="forbid")

    title: Annotated[str, Field(min_length=1, max_length=200)]
    week_start_date: date
    notes: str | None = Field(default=None, max_length=600)
    days: list[DayIn] = Field(min_length=1, max_length=MAX_PLAN_DAYS)
    expected_revision: int | None = Field(default=None, ge=1)

    @field_validator("days")
    @classmethod
    def _unique_dates(cls, days: list[DayIn]) -> list[DayIn]:
        seen = {d.day_date for d in days}
        if len(seen) != len(days):
            raise ValueError("Days must be unique.")
        return days


class GeneratePlanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    week_start_date: date
    title: str | None = Field(default=None, max_length=200)
    include_snacks: bool = True
    notes: str | None = Field(default=None, max_length=600)


class CopyPlanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    week_start_date: date
    title: str | None = Field(default=None, max_length=200)


class CreateBlankPlanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    week_start_date: date
    title: str | None = Field(default=None, max_length=200)


class IngredientOut(BaseModel):
    name: str
    quantity: float
    unit: str


class MealOut(BaseModel):
    meal: str
    title: str
    servings: int
    cooking_minutes: int | None
    ingredients: list[IngredientOut]
    notes: str | None


class DayOut(BaseModel):
    day_date: date
    meals: list[MealOut]


class PlanOut(BaseModel):
    """API representation of a stored plan (also used as the persisted plan_json shape)."""

    schema_version: int = 1
    days: list[DayOut]
    notes: str | None = None


class PlanSummary(BaseModel):
    id: uuid.UUID
    title: str
    week_start_date: date
    source: str
    status: str
    revision: int
    day_count: int
    meal_count: int
    created_at: datetime
    updated_at: datetime


class PlanDetail(PlanSummary):
    notes: str | None
    plan: PlanOut
    model_meta: dict | None
    estimate: dict | None  # cached nutrition estimate, or null
    estimated_at: datetime | None


class ConstraintViolation(BaseModel):
    day_date: str
    meal: str
    entry_title: str
    ingredient: str
    code: str
    reason: str


class PlanWarnings(BaseModel):
    cooking_time: list[dict] = Field(default_factory=list)


class PlanCapabilities(BaseModel):
    text_provider_configured: bool
    text_provider: str | None = None
    text_provider_external: bool = False
    text_model: str | None = None
    message: str | None = None
    nutrition_sources_configured: bool = False