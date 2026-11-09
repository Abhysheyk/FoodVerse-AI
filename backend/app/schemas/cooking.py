import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.ai.cooking import (
    MAX_INGREDIENTS, MAX_SERVINGS, MAX_STEPS, IngredientIn, RecipeDraft, StepIn, SubstitutionIn,
)
from app.ai.text import TextProviderInfo
from app.schemas.food import CalculationOut, TotalOut

CONTEXT_NOTE = (
    "Model-generated suggestion. Nutrition is never estimated by the model; link verified food "
    "data to calculate it. Cooking-safety notes are general guidance, not a guarantee."
)
ALLERGY_NOTE = (
    "Ingredient names were checked against your declared allergies and diets by this app, not by "
    "the model. Cross-contact and mislabelled ingredients cannot be ruled out."
)


class Ingredient(BaseModel):
    name: str
    quantity: float | None
    unit: str | None
    note: str | None
    optional: bool


class Step(BaseModel):
    number: int
    instruction: str
    duration_minutes: int | None


class Substitution(BaseModel):
    ingredient: str
    alternative: str
    note: str | None


class NutritionLink(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ingredient_index: int = Field(ge=0, lt=MAX_INGREDIENTS)
    food_ref: str = Field(min_length=1, max_length=8000)
    grams: float = Field(gt=0, le=5000)


class AttachNutritionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    links: list[NutritionLink] = Field(min_length=1, max_length=MAX_INGREDIENTS)


class NutritionAttachment(BaseModel):
    whole_recipe: CalculationOut
    per_serving: dict[str, TotalOut]
    basis: str
    servings: int
    linked_items: int
    note: str = (
        "Calculated from food-composition records you linked, with fixed arithmetic. Foods you "
        "did not link are missing from these totals."
    )


class RecipeRead(BaseModel):
    id: uuid.UUID
    title: str
    description: str | None
    servings: int
    prep_minutes: int | None
    cook_minutes: int | None
    total_minutes: int | None
    equipment: list[str]
    ingredients: list[Ingredient]
    steps: list[Step]
    substitutions: list[Substitution]
    dietary_tags: list[str]
    allergen_warnings: list[str]
    safety_notes: list[str]
    beginner_notes: list[str]
    tips: list[str]
    status: str
    favorite: bool
    revision: int
    provider: TextProviderInfo | None
    nutrition: NutritionAttachment | None
    generated_at: datetime | None
    created_at: datetime
    updated_at: datetime
    context_note: str = CONTEXT_NOTE
    allergy_note: str = ALLERGY_NOTE


class RecipeSummary(BaseModel):
    id: uuid.UUID
    title: str
    servings: int
    total_minutes: int | None
    status: str
    favorite: bool
    dietary_tags: list[str]
    ingredient_count: int
    updated_at: datetime


class RecipeWrite(BaseModel):
    """Full replacement used by the edit form. Constraints are re-checked server-side."""

    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=600)
    servings: int = Field(ge=1, le=MAX_SERVINGS)
    prep_minutes: int | None = Field(default=None, ge=0, le=1440)
    cook_minutes: int | None = Field(default=None, ge=0, le=1440)
    equipment: list[str] = Field(default_factory=list, max_length=20)
    ingredients: list[IngredientIn] = Field(min_length=1, max_length=MAX_INGREDIENTS)
    steps: list[StepIn] = Field(min_length=1, max_length=MAX_STEPS)
    substitutions: list[SubstitutionIn] = Field(default_factory=list, max_length=20)
    dietary_tags: list[str] = Field(default_factory=list, max_length=12)
    tips: list[str] = Field(default_factory=list, max_length=12)
    beginner_notes: list[str] = Field(default_factory=list, max_length=10)
    safety_notes: list[str] = Field(default_factory=list, max_length=10)
    expected_revision: int | None = Field(default=None, ge=1)

    @field_validator("title")
    @classmethod
    def _title(cls, value: str) -> str:
        value = " ".join(value.split())
        if not value:
            raise ValueError("Title must not be blank.")
        return value

    def to_draft(self) -> RecipeDraft:
        return RecipeDraft(
            title=self.title, description=self.description, servings=self.servings,
            prep_minutes=self.prep_minutes, cook_minutes=self.cook_minutes,
            equipment=self.equipment, ingredients=self.ingredients, steps=self.steps,
            substitutions=self.substitutions, dietary_tags=self.dietary_tags,
            allergen_warnings=[], safety_notes=self.safety_notes,
            beginner_notes=self.beginner_notes, tips=self.tips,
        )


class FavoriteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    favorite: bool


class GenerateRecipeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["from_ingredients", "free"] = "from_ingredients"
    ingredients: list[Annotated[str, Field(min_length=1, max_length=80)]] = Field(
        default_factory=list, max_length=30
    )
    servings: int = Field(default=2, ge=1, le=MAX_SERVINGS)
    conversation_id: uuid.UUID | None = None


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str = Field(min_length=1, max_length=2000)
    conversation_id: uuid.UUID | None = None


class MessageOut(BaseModel):
    id: uuid.UUID
    role: str
    content: str
    recipe_id: uuid.UUID | None
    warnings: list[str]
    created_at: datetime


class ChatResponse(BaseModel):
    conversation_id: uuid.UUID
    user_message: MessageOut
    assistant_message: MessageOut
    recipe: RecipeRead | None
    provider: TextProviderInfo


class ConversationSummary(BaseModel):
    id: uuid.UUID
    title: str
    message_count: int
    created_at: datetime
    updated_at: datetime


class ConversationDetail(ConversationSummary):
    messages: list[MessageOut]
    recipes: list[RecipeSummary]


class TextCapability(BaseModel):
    configured: bool
    provider: str | None = None
    model: str | None = None
    external: bool = False
    message: str | None = None


class Choice(BaseModel):
    value: str
    label: str


class CookingCapabilities(BaseModel):
    text: TextCapability
    diets: list[Choice]
    max_servings: int = MAX_SERVINGS
    context_messages: int
    allergy_note: str = ALLERGY_NOTE
    context_note: str = CONTEXT_NOTE