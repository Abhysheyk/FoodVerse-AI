import re
import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.domain.hygiene import (
    CERTAINTY_LABELS, CATEGORY_LABELS, LOCATION_TYPE_LABELS, SEVERITY_LABELS,
    STATUS_LABELS, Certainty, FindingCategory, InspectionStatus, LocationType, Severity,
)
from app.schemas.food import VisionCapability

_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
MAX_PHOTOS = 8


def _clean(value: str) -> str:
    return " ".join(_CONTROL.sub(" ", value).split())


class Choice(BaseModel):
    value: str
    label: str


class ChecklistItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    item_id: str = Field(min_length=1, max_length=64)
    label: str = Field(min_length=1, max_length=200)
    checked: bool = False
    note: str | None = Field(default=None, max_length=300)

    @field_validator("label", "note")
    @classmethod
    def _clean_text(cls, v: str | None) -> str | None:
        if v is None:
            return None
        cleaned = _clean(v)
        return cleaned or None


class FindingInput(BaseModel):
    """What the client sends when creating or editing a finding."""

    model_config = ConfigDict(extra="forbid")

    finding_id: uuid.UUID | None = None  # None = new finding
    source: Literal["model", "user"] = "user"
    category: FindingCategory
    severity: Severity
    description: str = Field(min_length=1, max_length=400)
    location: str = Field(default="", max_length=200)
    certainty: Certainty = Certainty.CLEARLY_VISIBLE
    evidence_media_id: uuid.UUID | None = None
    evidence_description: str | None = Field(default=None, max_length=300)
    user_note: str | None = Field(default=None, max_length=500)

    @field_validator("description")
    @classmethod
    def _desc(cls, v: str) -> str:
        cleaned = _clean(v)
        if not cleaned:
            raise ValueError("Description must not be blank.")
        return cleaned


class InspectionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    location_name: str = Field(min_length=1, max_length=120)
    location_type: LocationType
    area: str | None = Field(default=None, max_length=120)
    media_ids: list[uuid.UUID] = Field(default_factory=list, max_length=MAX_PHOTOS)
    notes: str | None = Field(default=None, max_length=2000)

    @field_validator("location_name", "area", "notes")
    @classmethod
    def _clean(cls, v: str | None) -> str | None:
        return (_clean(v) or None) if v is not None else None

    @field_validator("media_ids")
    @classmethod
    def _dedupe(cls, v: list[uuid.UUID]) -> list[uuid.UUID]:
        return list(dict.fromkeys(v))


class InspectionUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_revision: int | None = Field(default=None, ge=1)
    location_name: str | None = Field(default=None, min_length=1, max_length=120)
    location_type: LocationType | None = None
    area: str | None = Field(default=None, max_length=120)
    media_ids: list[uuid.UUID] | None = Field(default=None, max_length=MAX_PHOTOS)
    notes: str | None = Field(default=None, max_length=2000)
    checklist: list[ChecklistItem] | None = Field(default=None, max_length=30)
    findings: list[FindingInput] | None = Field(default=None, max_length=80)

    @field_validator("media_ids")
    @classmethod
    def _dedupe(cls, v: list[uuid.UUID] | None) -> list[uuid.UUID] | None:
        return list(dict.fromkeys(v)) if v is not None else None


class StatusChange(BaseModel):
    model_config = ConfigDict(extra="forbid")
    review_notes: str | None = Field(default=None, max_length=1000)

    @field_validator("review_notes")
    @classmethod
    def _clean(cls, v: str | None) -> str | None:
        return (_clean(v) or None) if v else None


# ---- responses ----


class FindingOut(BaseModel):
    finding_id: uuid.UUID
    source: Literal["model", "user", "user_edited"]
    category: FindingCategory
    category_label: str
    severity: Severity
    severity_label: str
    description: str
    location: str
    certainty: Certainty
    certainty_label: str
    evidence_media_id: uuid.UUID | None
    evidence_description: str | None
    user_note: str | None
    suggested_action: str


class LocationOut(BaseModel):
    name: str
    type: str
    type_label: str
    area: str | None


class HygieneAudit(BaseModel):
    """The full audit stored in analysis_records.result."""

    schema_version: int = 1
    location: LocationOut
    checklist: list[ChecklistItem]
    findings: list[FindingOut]
    notes: str | None = None
    disclosures: list[str]
    not_assessable: list[str]
    # Preserved verbatim from the model for the audit trail. Never shown as advice.
    model_limitations: list[str] = Field(default_factory=list)
    model_notes: str | None = None
    withheld_text_count: int = 0
    provider: dict | None = None
    analyzed_at: datetime | None = None
    generated_at: datetime


class InspectionSummary(BaseModel):
    id: uuid.UUID
    location_name: str
    location_type: str
    location_type_label: str
    area: str | None
    status: InspectionStatus
    status_label: str
    finding_count: int
    highest_severity: str | None
    photo_count: int
    revision: int
    reviewed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class InspectionDetail(InspectionSummary):
    media_ids: list[uuid.UUID]
    notes: str | None
    review_notes: str | None
    result: HygieneAudit


class HygieneCapabilities(BaseModel):
    vision: VisionCapability
    location_types: list[Choice]
    statuses: list[Choice]
    default_checklist: list[ChecklistItem]
    max_photos: int = MAX_PHOTOS


class HygieneMetaChoices(BaseModel):
    category: FindingCategory
    label: str
    suggested_action: str


def location_out(name: str, type_value: str, area: str | None) -> LocationOut:
    try:
        lt = LocationType(type_value)
    except ValueError:
        lt = LocationType.OTHER
    return LocationOut(name=name, type=lt.value, type_label=LOCATION_TYPE_LABELS[lt], area=area)


def category_label(c: FindingCategory) -> str:
    return CATEGORY_LABELS[c]


__all__ = [
    "CATEGORY_LABELS", "CERTAINTY_LABELS", "SEVERITY_LABELS", "STATUS_LABELS",
    "Choice", "ChecklistItem", "FindingInput", "FindingOut", "HygieneAudit",
    "HygieneCapabilities", "HygieneMetaChoices", "InspectionCreate", "InspectionDetail",
    "InspectionSummary", "InspectionUpdate", "LocationOut", "StatusChange",
    "category_label", "location_out",
]