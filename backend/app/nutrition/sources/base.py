from typing import Protocol

from app.nutrition.types import FoodCandidate


class NutritionSource(Protocol):
    name: str
    label: str

    def search(self, query: str, limit: int) -> list[FoodCandidate]:
        """Return matches, or raise NutritionSourceError. Never return invented values."""
        ...
