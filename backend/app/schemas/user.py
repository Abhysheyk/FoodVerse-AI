import re
import uuid
from datetime import datetime
from typing import Literal, get_args

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.models.preferences import UnitSystem

DietaryPreference = Literal[
    "vegetarian",
    "vegan",
    "eggetarian",
    "pescatarian",
    "jain",
    "halal",
    "kosher",
    "gluten_free",
    "lactose_free",
]
DIETARY_PREFERENCES: tuple[str, ...] = get_args(DietaryPreference)

MAX_ALLERGIES = 20
# Letters/digits first, then letters, digits, space, apostrophe, hyphen or slash.
_ALLERGY_RE = re.compile(r"^[^\W_][\w '\-/]*$")


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: EmailStr
    display_name: str
    created_at: datetime


class PreferencesRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    unit_system: UnitSystem
    dietary_preferences: list[str]
    allergies: list[str]
    updated_at: datetime


class PreferencesUpdate(BaseModel):
    """Full replacement of the user's preferences (PUT semantics)."""

    model_config = ConfigDict(extra="forbid")

    unit_system: UnitSystem
    dietary_preferences: list[DietaryPreference] = Field(default_factory=list, max_length=20)
    allergies: list[str] = Field(default_factory=list, max_length=MAX_ALLERGIES)

    @field_validator("dietary_preferences")
    @classmethod
    def _dedupe_dietary(cls, values: list[str]) -> list[str]:
        return list(dict.fromkeys(values))

    @field_validator("allergies")
    @classmethod
    def _normalise_allergies(cls, values: list[str]) -> list[str]:
        cleaned: list[str] = []
        for raw in values:
            item = " ".join(raw.split()).lower()
            if not 1 <= len(item) <= 50:
                raise ValueError("Each allergy must be 1-50 characters.")
            if not _ALLERGY_RE.match(item):
                raise ValueError("Allergies may contain only letters, digits, spaces, - ' and /.")
            cleaned.append(item)
        return list(dict.fromkeys(cleaned))
