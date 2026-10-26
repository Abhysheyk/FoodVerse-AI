import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models import MealCategory
from app.schemas.food import MAX_MEAL_ITEMS, FoodItemInput, MealAudit


class MealWrite(BaseModel):
    """Create or fully replace a meal. Totals are never accepted from the client."""

    model_config = ConfigDict(extra="forbid")

    items: list[FoodItemInput] = Field(min_length=1, max_length=MAX_MEAL_ITEMS)
    eaten_at: datetime
    category: MealCategory
    notes: Annotated[str, Field(max_length=1000)] | None = None
    media_id: uuid.UUID | None = None
    scan_ref: str | None = Field(default=None, max_length=20_000)
    # Updates only: reject the write if the meal was changed elsewhere in the meantime.
    expected_revision: int | None = Field(default=None, ge=1)

    @field_validator("eaten_at")
    @classmethod
    def _plausible_time(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("eaten_at must include a time zone offset.")
        now = datetime.now(UTC)
        if value > now + timedelta(days=1):
            raise ValueError("A meal cannot be logged more than a day in the future.")
        if value < now - timedelta(days=3650):
            raise ValueError("That date is too far in the past.")
        return value.astimezone(UTC)

    @field_validator("notes")
    @classmethod
    def _notes(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None


class BriefTotal(BaseModel):
    low: float | None
    high: float | None
    complete: bool


class MealSummary(BaseModel):
    id: uuid.UUID
    title: str
    items_label: str
    category: MealCategory
    eaten_at: datetime
    item_count: int
    calories: BriefTotal
    media_id: uuid.UUID | None
    revision: int
    created_at: datetime
    updated_at: datetime


class MealDetail(MealSummary):
    notes: str | None
    result: MealAudit
