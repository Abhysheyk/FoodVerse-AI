"""The product's feature modules. Single source of truth for the UI's module entry points.

`available` becomes True only when a module's backend is actually implemented, so the
interface can never advertise a feature that does nothing.
"""

from dataclasses import dataclass

from app.models import ModuleKey


@dataclass(frozen=True)
class ModuleInfo:
    key: ModuleKey
    title: str
    description: str
    available: bool = False


MODULES: tuple[ModuleInfo, ...] = (
    ModuleInfo(
        ModuleKey.FOOD_RECOGNITION,
        "Food recognition & nutrition",
        "Identify a dish from a photo, confirm the food and portion, and see nutrition "
        "calculated from a cited food-composition table.",
    ),
    ModuleInfo(
        ModuleKey.FRESHNESS,
        "Freshness check",
        "An advisory look at visible freshness and spoilage signs, with clear uncertainty.",
    ),
    ModuleInfo(
        ModuleKey.HYGIENE,
        "Kitchen hygiene",
        "An advisory review of visible hygiene and safety concerns in kitchen photos.",
    ),
    ModuleInfo(
        ModuleKey.COOKING,
        "Cooking assistant",
        "Recipe ideas and step-by-step help that respect your allergies and diet.",
    ),
    ModuleInfo(
        ModuleKey.MEAL_PLANNING,
        "Meal planning",
        "Personalised plans, nutrition tracking and grocery lists.",
    ),
)

MODULES_BY_KEY: dict[ModuleKey, ModuleInfo] = {m.key: m for m in MODULES}
