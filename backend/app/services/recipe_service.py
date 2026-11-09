"""Recipe persistence, scaling, editing and verified-nutrition linking.

Nothing here trusts a client with numbers or with a model's claims:
  * totals are computed by `app.domain.nutrition_calc` from signed `food_ref`s;
  * every write re-runs the deterministic allergen/diet gate.
"""

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.ai.cooking import RecipeDraft
from app.ai.text import TextProviderInfo
from app.core.config import Settings
from app.core.errors import AppError, ConflictError, NotFoundError
from app.core.signed_refs import InvalidRefError, verify_ref
from app.domain import nutrition_calc as calc  # noqa: F401  (kept for type parity with food_service)
from app.domain.recipes import (
    RecipeError,
    allergy_disclosure,
    divide_totals,
    enforce,
    scale_recipe,
)
from app.models import AnalysisRecord, AnalysisStatus, ModuleKey, User
from app.models.cooking import Recipe, RecipeStatus
from app.repositories import recipes as repo
from app.schemas.common import Page
from app.schemas.cooking import (
    AttachNutritionRequest,
    Ingredient,
    NutritionAttachment,
    RecipeRead,
    RecipeSummary,
    RecipeWrite,
    Step,
    Substitution,
)
from app.schemas.food import (
    CalculationOut,
    FoodItemInput,
    FoodSnapshot,
)
from app.services import food_service
from app.services.preferences_service import get_preferences

logger = logging.getLogger("app.cooking")


class DietaryConflictError(AppError):
    status_code = 422
    code = "dietary_conflict"


# --------------------------------------------------------------------------- row <-> draft
def draft_to_row_values(draft: RecipeDraft) -> dict[str, Any]:
    return {
        "title": draft.title,
        "description": draft.description,
        "servings": draft.servings,
        "prep_minutes": draft.prep_minutes,
        "cook_minutes": draft.cook_minutes,
        "equipment": list(draft.equipment),
        "ingredients": [i.model_dump() for i in draft.ingredients],
        "steps": [
            {
                "number": n,
                "instruction": s.instruction,
                "duration_minutes": s.duration_minutes,
            }
            for n, s in enumerate(draft.steps, start=1)
        ],
        "substitutions": [s.model_dump() for s in draft.substitutions],
        "dietary_tags": list(draft.dietary_tags),
        "allergen_warnings": list(draft.allergen_warnings),
        "safety_notes": list(draft.safety_notes),
        "tips": list(draft.tips),
        "beginner_notes": list(draft.beginner_notes),
    }


def draft_from_row(recipe: Recipe) -> RecipeDraft:
    return RecipeDraft(
        title=recipe.title,
        description=recipe.description,
        servings=recipe.servings,
        prep_minutes=recipe.prep_minutes,
        cook_minutes=recipe.cook_minutes,
        equipment=list(recipe.equipment or []),
        ingredients=list(recipe.ingredients or []),
        steps=[
            {
                "instruction": s.get("instruction", ""),
                "duration_minutes": s.get("duration_minutes"),
            }
            for s in (recipe.steps or [])
        ],
        substitutions=list(recipe.substitutions or []),
        dietary_tags=list(recipe.dietary_tags or []),
        allergen_warnings=list(recipe.allergen_warnings or []),
        safety_notes=list(recipe.safety_notes or []),
        beginner_notes=list(recipe.beginner_notes or []),
        tips=list(recipe.tips or []),
    )


def to_read(recipe: Recipe, draft: RecipeDraft | None = None) -> RecipeRead:
    d = draft or draft_from_row(recipe)
    provider = (
        TextProviderInfo.model_validate(recipe.provider) if recipe.provider else None
    )
    nutrition = (
        NutritionAttachment.model_validate(recipe.nutrition) if recipe.nutrition else None
    )
    return RecipeRead(
        id=recipe.id,
        title=d.title,
        description=d.description,
        servings=d.servings,
        prep_minutes=d.prep_minutes,
        cook_minutes=d.cook_minutes,
        total_minutes=d.total_minutes,
        equipment=list(d.equipment),
        ingredients=[Ingredient(**i.model_dump()) for i in d.ingredients],
        steps=[
            Step(number=n, instruction=s.instruction, duration_minutes=s.duration_minutes)
            for n, s in enumerate(d.steps, start=1)
        ],
        substitutions=[Substitution(**s.model_dump()) for s in d.substitutions],
        dietary_tags=list(d.dietary_tags),
        allergen_warnings=list(d.allergen_warnings),
        safety_notes=list(d.safety_notes),
        beginner_notes=list(d.beginner_notes),
        tips=list(d.tips),
        status=recipe.status.value,
        favorite=recipe.favorite,
        revision=recipe.revision,
        provider=provider,
        nutrition=nutrition,
        generated_at=recipe.generated_at,
        created_at=recipe.created_at,
        updated_at=recipe.updated_at,
    )


def summary(recipe: Recipe) -> RecipeSummary:
    total = None
    if recipe.prep_minutes is not None or recipe.cook_minutes is not None:
        total = (recipe.prep_minutes or 0) + (recipe.cook_minutes or 0)
    return RecipeSummary(
        id=recipe.id,
        title=recipe.title,
        servings=recipe.servings,
        total_minutes=total,
        status=recipe.status.value,
        favorite=recipe.favorite,
        dietary_tags=list(recipe.dietary_tags or []),
        ingredient_count=len(recipe.ingredients or []),
        updated_at=recipe.updated_at,
    )


# --------------------------------------------------------------------------- gate
def get_owned_or_404(db: Session, user: User, recipe_id: uuid.UUID) -> Recipe:
    recipe = repo.get_owned(db, recipe_id, user.id)
    if recipe is None:  # identical answer for "missing" and "someone else's"
        raise NotFoundError("Recipe not found.", code="recipe_not_found")
    return recipe


def assert_allowed(draft: RecipeDraft, allergies: list[str], diets: list[str]) -> list[str]:
    conflicts = enforce(draft, allergies, diets)
    if conflicts:
        raise DietaryConflictError(
            "That recipe conflicts with your declared allergies or diet, so it was not kept.",
            details=[{"field": "ingredients", "message": c.message} for c in conflicts],
        )
    disclosure = allergy_disclosure(draft, allergies)
    return list(disclosure["warnings"])


# --------------------------------------------------------------------------- lifecycle
def create_suggested(
    db: Session,
    user: User,
    draft: RecipeDraft,
    *,
    provider: TextProviderInfo | None,
    conversation_id: uuid.UUID | None,
) -> Recipe:
    """Persist a validated, allowed suggestion. Not listed until the user keeps it."""
    prefs = get_preferences(db, user)
    warnings = assert_allowed(draft, prefs.allergies, prefs.dietary_preferences)
    row = Recipe(
        owner_id=user.id,
        conversation_id=conversation_id,
        status=RecipeStatus.SUGGESTED,
        provider=provider.model_dump() if provider else None,
        generated_at=datetime.now(UTC),
        allergen_warnings=list(draft.allergen_warnings) + warnings,
        **draft_to_row_values(draft),
    )
    return repo.add(db, row)


def _audit_snapshot(recipe: Recipe) -> dict[str, Any]:
    """JSON-safe snapshot of the persisted recipe, for the linked AnalysisRecord."""
    return to_read(recipe).model_dump(mode="json")


def save_recipe(db: Session, user: User, recipe_id: uuid.UUID) -> RecipeRead:
    recipe = get_owned_or_404(db, user, recipe_id)
    if recipe.status is RecipeStatus.SAVED:
        return to_read(recipe)

    prefs = get_preferences(db, user)
    draft = draft_from_row(recipe)
    assert_allowed(draft, prefs.allergies, prefs.dietary_preferences)

    recipe.status = RecipeStatus.SAVED
    recipe.analysis_id = recipe.id
    db.flush()
    db.refresh(recipe)  # so `updated_at` etc. reflect the change before we build the audit

    record = AnalysisRecord(
        id=recipe.id,
        owner_id=user.id,
        module=ModuleKey.COOKING,
        status=AnalysisStatus.COMPLETED,
        title=recipe.title[:200],
        summary=f"{len(draft.ingredients)} ingredients · serves {draft.servings}",
        result={"schema_version": 1, "recipe": _audit_snapshot(recipe)},
    )
    db.add(record)
    db.commit()
    db.refresh(recipe)
    logger.info("recipe_saved user_id=%s recipe_id=%s", user.id, recipe.id)
    return to_read(recipe)


def set_favorite(
    db: Session, user: User, recipe_id: uuid.UUID, favorite: bool
) -> RecipeRead:
    recipe = get_owned_or_404(db, user, recipe_id)
    recipe.favorite = favorite
    if favorite:
        recipe.status = RecipeStatus.SAVED  # favouriting keeps it
    db.commit()
    db.refresh(recipe)
    return to_read(recipe)


def update_recipe(
    db: Session, user: User, recipe_id: uuid.UUID, data: RecipeWrite
) -> RecipeRead:
    recipe = get_owned_or_404(db, user, recipe_id)
    if data.expected_revision is not None and data.expected_revision != recipe.revision:
        raise ConflictError(
            "This recipe was changed somewhere else. Reload it and try again.",
            code="recipe_revision_conflict",
        )
    prefs = get_preferences(db, user)
    draft = data.to_draft()
    warnings = assert_allowed(draft, prefs.allergies, prefs.dietary_preferences)

    for field, value in draft_to_row_values(draft).items():
        setattr(recipe, field, value)
    recipe.allergen_warnings = list(draft.allergen_warnings) + warnings
    recipe.revision += 1
    db.flush()
    db.refresh(recipe)

    if recipe.status is RecipeStatus.SAVED:
        record = db.get(AnalysisRecord, recipe.id)
        if record is not None:
            record.title = recipe.title[:200]
            record.result = {"schema_version": 1, "recipe": _audit_snapshot(recipe)}

    db.commit()
    db.refresh(recipe)
    logger.info(
        "recipe_updated user_id=%s recipe_id=%s rev=%s",
        user.id,
        recipe_id,
        recipe.revision,
    )
    return to_read(recipe)


def delete_recipe(db: Session, user: User, recipe_id: uuid.UUID) -> None:
    recipe = get_owned_or_404(db, user, recipe_id)
    record = db.get(AnalysisRecord, recipe.id) if recipe.analysis_id else None
    db.delete(recipe)
    if record is not None:
        db.delete(record)
    db.commit()
    logger.info("recipe_deleted user_id=%s recipe_id=%s", user.id, recipe_id)


def list_recipes(
    db: Session,
    user: User,
    *,
    page: int,
    page_size: int,
    query: str | None,
    favorite: bool | None,
) -> Page[RecipeSummary]:
    cleaned = " ".join((query or "").split())[:80] or None
    rows, total = repo.list_page(
        db,
        user.id,
        limit=page_size,
        offset=(page - 1) * page_size,
        query=cleaned,
        favorite=favorite,
    )
    return Page.build([summary(r) for r in rows], total, page, page_size)


def scaled(recipe: Recipe, servings: int) -> RecipeRead:
    draft = draft_from_row(recipe)
    try:
        return to_read(recipe, scale_recipe(draft, servings))
    except RecipeError as exc:
        raise AppError(str(exc), code="invalid_servings", status_code=422) from None


def attach_nutrition(
    db: Session,
    settings: Settings,
    user: User,
    recipe_id: uuid.UUID,
    req: AttachNutritionRequest,
) -> RecipeRead:
    recipe = get_owned_or_404(db, user, recipe_id)
    ingredients = list(recipe.ingredients or [])
    items: list[FoodItemInput] = []
    seen: set[int] = set()
    for link in req.links:
        if link.ingredient_index in seen:
            raise AppError(
                "Each ingredient can be linked once.", code="invalid_link", status_code=422
            )
        seen.add(link.ingredient_index)
        if link.ingredient_index >= len(ingredients):
            raise AppError(
                "That ingredient does not exist.", code="invalid_link", status_code=422
            )
        try:
            payload = verify_ref(settings, "food", user.id, link.food_ref)
            FoodSnapshot.model_validate(payload)  # validate shape; service recomputes below
        except (InvalidRefError, ValidationError):
            raise AppError(
                "A nutrition reference is invalid or has expired.",
                code="invalid_reference",
                status_code=422,
            ) from None
        items.append(
            FoodItemInput(
                name=str(ingredients[link.ingredient_index].get("name", "ingredient"))[:80],
                food_ref=link.food_ref,
                portion={"kind": "weight", "amount": link.grams, "unit": "g"},
            )
        )

    audit = food_service.calculate_audit(
        settings, user, items, scan_ref=None, existing=None
    )
    whole = CalculationOut.model_validate(
        audit.model_dump(exclude={"schema_version", "model_observations"})
    )
    attachment = NutritionAttachment(
        whole_recipe=whole,
        per_serving=divide_totals(whole.totals, recipe.servings),
        basis="whole recipe, from food-composition records the user linked",
        servings=recipe.servings,
        linked_items=len(items),
    )
    recipe.nutrition = attachment.model_dump(mode="json")
    db.commit()
    db.refresh(recipe)
    logger.info(
        "recipe_nutrition_linked user_id=%s recipe_id=%s items=%d",
        user.id,
        recipe_id,
        len(items),
    )
    return to_read(recipe)