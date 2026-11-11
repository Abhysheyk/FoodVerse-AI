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

DietaryPattern = Literal[
    "omnivore", "vegetarian", "vegan", "eggetarian", "pescatarian",
    "jain", "halal", "kosher",
]
BudgetLevel = Literal["any", "budget", "moderate", "premium"]


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
    dietary_pattern: str | None = None
    excluded_ingredients: list[str] = []
    preferred_cuisines: list[str] = []
    budget: str = "any"
    max_cooking_minutes: int | None = None
    default_servings: int = 1
    pantry_ingredients: list[str] = []
    updated_at: datetime


class PreferencesUpdate(BaseModel):
    """Full replacement of the user's preferences (PUT semantics)."""

    model_config = ConfigDict(extra="forbid")

    unit_system: UnitSystem
    dietary_preferences: list[DietaryPreference] = Field(default_factory=list, max_length=20)
    allergies: list[str] = Field(default_factory=list, max_length=MAX_ALLERGIES)
    dietary_pattern: DietaryPattern | None = None
    excluded_ingredients: list[str] = Field(default_factory=list, max_length=50)
    preferred_cuisines: list[str] = Field(default_factory=list, max_length=20)
    budget: BudgetLevel = "any"
    max_cooking_minutes: int | None = Field(default=None, ge=5, le=720)
    default_servings: int = Field(default=1, ge=1, le=20)
    pantry_ingredients: list[str] = Field(default_factory=list, max_length=100)

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

    @field_validator("excluded_ingredients", "pantry_ingredients")
    @classmethod
    def _normalise_list(cls, values: list[str]) -> list[str]:
        cleaned = [" ".join(v.split()).lower()[:80] for v in values if v.strip()]
        return list(dict.fromkeys(cleaned))

    @field_validator("preferred_cuisines")
    @classmethod
    def _cuisines(cls, values: list[str]) -> list[str]:
        cleaned = [" ".join(v.split())[:32] for v in values if v.strip()]
        return list(dict.fromkeys(cleaned))


class ProfileUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: str = Field(min_length=1, max_length=80)

    @field_validator("display_name")
    @classmethod
    def _clean_name(cls, value: str) -> str:
        value = " ".join(value.split())
        if not value:
            raise ValueError("Display name must not be blank.")
        return value


class PasswordChange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=10, max_length=128)
