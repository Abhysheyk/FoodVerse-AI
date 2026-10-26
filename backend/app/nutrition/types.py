from pydantic import BaseModel, Field


class FoodCandidate(BaseModel):
    """One matching food from a trusted source, with values per 100 g exactly as reported."""

    source: str  # usda_fdc | open_food_facts | local_reference
    source_label: str
    source_id: str
    name: str
    brand: str | None = None
    data_type: str | None = None
    per_100g: dict[str, float]  # only nutrients the source actually supplied
    serving_grams: float | None = None  # only when the source states a serving in grams
    serving_label: str | None = None
    attribution: str
    url: str | None = None
    notes: list[str] = Field(default_factory=list)  # e.g. "Calories converted from kJ"


class NutritionSourceError(Exception):
    def __init__(self, status: str, message: str, retry_after: int | None = None) -> None:
        super().__init__(message)
        self.status = status  # unavailable | rate_limited | timeout
        self.message = message
        self.retry_after = retry_after
