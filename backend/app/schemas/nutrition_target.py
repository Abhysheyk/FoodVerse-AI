from pydantic import BaseModel, ConfigDict, Field, model_validator


class NutritionTarget(BaseModel):
    """All fields are optional. The user sets these themselves; nothing is inferred from
    data. This is the shape used for PUT requests and for reading back from storage."""

    model_config = ConfigDict(extra="forbid")

    calories_min: int | None = Field(default=None, ge=0, le=20000)
    calories_max: int | None = Field(default=None, ge=0, le=20000)
    protein_g_min: float | None = Field(default=None, ge=0, le=2000)
    carbs_g_min: float | None = Field(default=None, ge=0, le=2000)
    fat_g_min: float | None = Field(default=None, ge=0, le=2000)
    fiber_g_min: float | None = Field(default=None, ge=0, le=500)
    notes: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def _ordered_range(self) -> "NutritionTarget":
        if (
            self.calories_min is not None
            and self.calories_max is not None
            and self.calories_min > self.calories_max
        ):
            raise ValueError("calories_min must not exceed calories_max.")
        return self


class NutritionTargetRead(NutritionTarget):
    """Response shape. Identical to NutritionTarget today, but kept separate so the response
    can evolve (e.g. add computed fields) without changing the request schema."""