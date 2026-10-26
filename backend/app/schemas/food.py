import re
import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.ai.vision import MAX_ITEMS, VisionProviderInfo

MAX_MEAL_ITEMS = 30
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")

UNCERTAINTY_NOTE = (
    "Item names come from an image model and may be wrong. This model does not give a reliable "
    "confidence score, so none is shown: please check every item."
)
DISCLAIMER = (
    "Estimates only, calculated from the food-composition data and the portions you entered. "
    "They are not medical or dietary advice. Check labels and consult a qualified professional "
    "for allergies or medical diets."
)
CALCULATION_METHOD = "nutrient per 100 g x grams eaten / 100, summed over items"


class WeightPortion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["weight"]
    amount: float = Field(gt=0, le=100_000)
    unit: Literal["g", "kg", "oz", "lb"]


class RangePortion(BaseModel):
    """A user-supplied estimate range. Never filled in automatically."""

    model_config = ConfigDict(extra="forbid")
    kind: Literal["range"]
    min_amount: float = Field(gt=0, le=100_000)
    max_amount: float = Field(gt=0, le=100_000)
    unit: Literal["g", "kg", "oz", "lb"]


class ServingsPortion(BaseModel):
    """N servings, where one serving is the gram weight stated by the food's own source."""

    model_config = ConfigDict(extra="forbid")
    kind: Literal["servings"]
    count: float = Field(gt=0, le=100)


Portion = Annotated[WeightPortion | RangePortion | ServingsPortion, Field(discriminator="kind")]


def clean_name(value: str) -> str:
    value = " ".join(_CONTROL.sub(" ", value).split())
    if not value:
        raise ValueError("Name must not be blank.")
    return value


class FoodSnapshot(BaseModel):
    """The trusted source record chosen for an item, frozen at selection time (audit)."""

    source: str
    source_label: str
    source_id: str
    name: str
    brand: str | None = None
    data_type: str | None = None
    per_100g: dict[str, float]
    serving_grams: float | None = None
    serving_label: str | None = None
    attribution: str
    url: str | None = None
    notes: list[str] = Field(default_factory=list)


class FoodItemInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item_id: uuid.UUID | None = None  # an existing item of the meal being edited
    observed_id: int | None = Field(default=None, ge=0, lt=MAX_ITEMS)  # index in the scan result
    name: Annotated[str, Field(min_length=1, max_length=80)]
    food_ref: str | None = Field(default=None, max_length=8000)  # from /nutrition/search
    clear_food: bool = False  # drop the previously chosen nutrition match
    portion: Portion | None = None

    @field_validator("name")
    @classmethod
    def _name(cls, value: str) -> str:
        return clean_name(value)


class CalculateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[FoodItemInput] = Field(min_length=1, max_length=MAX_MEAL_ITEMS)
    scan_ref: str | None = Field(default=None, max_length=20_000)
    meal_id: uuid.UUID | None = None  # resolves item_id / clear_food against a saved meal


class ScanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    media_id: uuid.UUID


class ObservedFood(BaseModel):
    observed_id: int
    name: str
    description: str
    ambiguous: bool
    alternatives: list[str]


class ScanResponse(BaseModel):
    scan_ref: str
    media_id: uuid.UUID
    provider: VisionProviderInfo
    items: list[ObservedFood]
    notes: str | None
    uncertainty_note: str = UNCERTAINTY_NOTE
    generated_at: datetime


class NutrientValueOut(BaseModel):
    low: float
    high: float
    unit: str


class PortionOut(BaseModel):
    description: str
    grams_low: float
    grams_high: float
    uncertain: bool


class ItemCalcOut(BaseModel):
    item_id: uuid.UUID
    name: str
    origin: Literal["model", "model_edited", "user_added"]
    observed_name: str | None
    food: FoodSnapshot | None
    portion_input: Portion | None
    portion: PortionOut | None
    nutrients: dict[str, NutrientValueOut]
    not_reported: list[str]
    warnings: list[str]


class TotalOut(BaseModel):
    key: str
    label: str
    unit: str
    low: float | None
    high: float | None
    complete: bool
    contributing_items: int
    missing_items: list[str]


class CalculationOut(BaseModel):
    items: list[ItemCalcOut]
    totals: dict[str, TotalOut]
    warnings: list[str]
    unit_basis: str = "per 100 g, as published by each source"
    method: str = CALCULATION_METHOD
    disclaimer: str = DISCLAIMER


class ModelObservations(BaseModel):
    """What the vision model actually said, as signed by the server at scan time."""

    provider: VisionProviderInfo
    media_id: uuid.UUID
    items: list[ObservedFood]
    notes: str | None
    generated_at: datetime
    uncertainty_note: str = UNCERTAINTY_NOTE


class MealAudit(CalculationOut):
    """The complete audit record stored in analysis_records.result."""

    schema_version: int = 1
    model_observations: ModelObservations | None = None


class CandidateOut(FoodSnapshot):
    food_ref: str


class SourceStatus(BaseModel):
    source: str
    label: str
    status: Literal["ok", "not_configured", "unavailable", "rate_limited", "timeout"]
    message: str | None = None


class NutritionSearchResponse(BaseModel):
    query: str
    results: list[CandidateOut]
    sources: list[SourceStatus]


class NutrientDefinition(BaseModel):
    key: str
    label: str
    unit: str
    core: bool


class NutritionStatus(BaseModel):
    sources: list[SourceStatus]
    nutrients: list[NutrientDefinition]
    any_configured: bool
    local_reference_records: int


class VisionCapability(BaseModel):
    configured: bool
    provider: str | None = None
    model: str | None = None
    external: bool = False  # True when photos would leave this machine/network
    message: str | None = None  # why it is not configured, in plain words


class FoodCapabilities(BaseModel):
    vision: VisionCapability
    nutrition: NutritionStatus


class BarcodeResponse(BaseModel):
    barcode: str
    result: CandidateOut | None
    sources: list[SourceStatus]


JsonDict = dict[str, Any]
