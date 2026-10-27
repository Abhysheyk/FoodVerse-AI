import re
import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.ai.vision import VisionProviderInfo
from app.domain.freshness import (
    FoodCategory,
    Packaging,
    StorageCondition,
)
from app.schemas.food import VisionCapability

_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
MIN_DATE = date(2000, 1, 1)

VERDICT_NOTICE = (
    "This is a description of what is visible in one image plus general food-safety guidance. "
    "It is not a statement that the food is safe, or unsafe, to eat, and there is no freshness "
    "score."
)


def _clean(value: str) -> str:
    return " ".join(_CONTROL.sub(" ", value).split())


class DurationIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    amount: int = Field(ge=0, le=8760)
    unit: Literal["hours", "days"]

    @model_validator(mode="after")
    def _bounded(self) -> "DurationIn":
        if self.unit == "days" and self.amount > 365:
            raise ValueError("Storage time cannot be more than 365 days.")
        return self

    @property
    def hours(self) -> int:
        return self.amount * (24 if self.unit == "days" else 1)


class AssessmentRequest(BaseModel):
    """What the user tells us. Nothing here is a model output or a verdict."""

    model_config = ConfigDict(extra="forbid")

    media_id: uuid.UUID | None = None
    # False: skip the image model and give guidance from the details alone (works offline).
    analyze_image: bool = True
    food_name: str = Field(min_length=1, max_length=80)
    food_category: FoodCategory
    storage_condition: StorageCondition = StorageCondition.UNKNOWN
    packaging: Packaging = Packaging.UNKNOWN
    storage_duration: DurationIn | None = None
    purchased_on: date | None = None
    use_by_date: date | None = None
    best_before_date: date | None = None
    assessed_on: date | None = None  # the user's local "today"; defaults to the server's UTC date
    notes: str | None = Field(default=None, max_length=500)

    @field_validator("food_name")
    @classmethod
    def _name(cls, value: str) -> str:
        value = _clean(value)
        if not value:
            raise ValueError("Name must not be blank.")
        return value

    @field_validator("notes")
    @classmethod
    def _notes(cls, value: str | None) -> str | None:
        return (_clean(value) or None) if value else None

    @field_validator("purchased_on", "use_by_date", "best_before_date")
    @classmethod
    def _plausible_date(cls, value: date | None) -> date | None:
        if value is not None and not (MIN_DATE <= value <= date(2100, 1, 1)):
            raise ValueError("That date is out of range.")
        return value

    @model_validator(mode="after")
    def _needs_photo_to_analyse(self) -> "AssessmentRequest":
        if self.analyze_image and self.media_id is None:
            raise ValueError("A photo is needed to analyse an image. Or choose guidance only.")
        return self


class ObservationView(BaseModel):
    feature: str
    feature_label: str
    description: str  # model-generated text
    location: str
    severity: str
    certainty: str


class ImageFindings(BaseModel):
    """What the model reported. Every string here is model-generated and labelled as such."""

    analysed: bool
    image_quality: str | None = None
    food_visible: bool | None = None
    matches_confirmed_food: str | None = None
    observations: list[ObservationView] = []
    limitations: list[str] = []
    notes: str | None = None
    withheld_text_count: int = 0


class ReasonOut(BaseModel):
    code: str
    text: str


class AssessmentOut(BaseModel):
    label: str
    label_text: str
    inconclusive_reasons: list[ReasonOut]


class SourceLink(BaseModel):
    name: str
    url: str


class AdviceOut(BaseModel):
    """Fixed-rule guidance. Never written by the model."""

    level: str
    headline: str
    reasons: list[ReasonOut]
    steps: list[str]
    category_cautions: list[str]
    general_notes: list[str]
    retake_tips: list[str]
    sources: list[SourceLink]


class InputsOut(BaseModel):
    storage_condition: str
    packaging: str
    storage_hours: int | None
    purchased_on: date | None
    use_by_date: date | None
    best_before_date: date | None
    assessed_on: date
    notes: str | None


class FoodOut(BaseModel):
    name: str
    category: str
    category_label: str


class FreshnessAudit(BaseModel):
    schema_version: int = 1
    food: FoodOut
    inputs: InputsOut
    findings: ImageFindings
    assessment: AssessmentOut
    advice: AdviceOut
    provider: VisionProviderInfo | None  # None when no image analysis was run
    classifier_result: None = None  # reserved: no validated classifier is shipped (ADR 0004)
    verdict_notice: str = VERDICT_NOTICE
    generated_at: datetime


class FreshnessSummary(BaseModel):
    id: uuid.UUID
    food_name: str
    food_category: str
    category_label: str
    label: str
    label_text: str
    advice_level: str
    image_analysed: bool
    media_id: uuid.UUID | None
    created_at: datetime


class FreshnessDetail(FreshnessSummary):
    result: FreshnessAudit


class Choice(BaseModel):
    value: str
    label: str


class FreshnessCapabilities(BaseModel):
    vision: VisionCapability
    categories: list[Choice]
    storage_conditions: list[Choice]
    packaging: list[Choice]
    classifier_enabled: bool = False
    verdict_notice: str = VERDICT_NOTICE
