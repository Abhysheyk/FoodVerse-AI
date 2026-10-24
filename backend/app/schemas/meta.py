from pydantic import BaseModel

from app.models.preferences import UnitSystem
from app.schemas.user import DIETARY_PREFERENCES

# Common allergen categories offered as suggestions in the UI. Users may enter their own;
# this list is a convenience, not a medical or regulatory classification.
COMMON_ALLERGENS: tuple[str, ...] = (
    "peanut",
    "tree nut",
    "milk",
    "egg",
    "wheat",
    "soy",
    "fish",
    "shellfish",
    "sesame",
    "mustard",
)


class PreferenceOptions(BaseModel):
    unit_systems: list[UnitSystem]
    dietary_preferences: list[str]
    common_allergens: list[str]

    @classmethod
    def current(cls) -> "PreferenceOptions":
        return cls(
            unit_systems=list(UnitSystem),
            dietary_preferences=list(DIETARY_PREFERENCES),
            common_allergens=list(COMMON_ALLERGENS),
        )
