"""Meal planning.

Generate → validate (strict schema) → enforce (allergies/exclusions/diet) → save.
Manual create → save empty. Copy → clone with a new week_start. Edit → replace whole plan.
Estimate → best-effort deterministic nutrition from existing trusted sources; cached.
"""

import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

from app.ai.meal_plan import (
    MEAL_PLAN_JSON_SCHEMA,
    build_meal_plan_prompt,
    parse_meal_plan_output,
)
from app.ai.text import TextProvider
from app.core.config import Settings
from app.core.errors import AppError, ConflictError, NotFoundError
from app.core.limits import limiter
from app.domain import meal_plan as rules
from app.domain.grocery import merge_ingredients
from app.models import MealPlan, MealPlanSource, MealPlanStatus, User
from app.nutrition.nutrients import NUTRIENT_BY_KEY
from app.nutrition.service import NutritionService
from app.repositories import meal_plans as repo
from app.schemas.common import Page
from app.schemas.meal_plan import (
    CopyPlanRequest,
    CreateBlankPlanRequest,
    DayOut,
    GeneratePlanRequest,
    IngredientOut,
    MealOut,
    PlanBody,
    PlanCapabilities,
    PlanDetail,
    PlanOut,
    PlanSummary,
    PlanWarnings,
)
from app.services import preferences_service

logger = logging.getLogger("app.meal_plans")
MAX_PLAN_DAYS = 7


class ConstraintViolationError(AppError):
    status_code = 422
    code = "meal_plan_constraint_violation"

    def __init__(self, violations: list[rules.Violation]) -> None:
        super().__init__(
            "The generated plan broke a hard constraint (allergy, exclusion or dietary "
            "pattern). Nothing was saved.",
        )
        self.violations = violations


class InvalidPlanError(AppError):
    status_code = 422
    code = "invalid_plan"


@dataclass(frozen=True)
class _EstimateBucket:
    kcal_low: float
    kcal_high: float
    kcal_complete: bool
    missing: list[str]


def _capabilities(settings: Settings, nutrition_configured: bool) -> PlanCapabilities:
    if settings.text_provider == "none":
        return PlanCapabilities(
            text_provider_configured=False,
            message=(
                "Meal plan generation is not configured. You can still create a blank plan and "
                "edit it manually. (Server setup: TEXT_PROVIDER=openai_compatible and "
                "ALLOW_EXTERNAL_AI_PROVIDERS=true with TEXT_API_BASE_URL, TEXT_API_KEY, "
                "TEXT_API_MODEL.)"
            ),
            nutrition_sources_configured=nutrition_configured,
        )
    return PlanCapabilities(
        text_provider_configured=True,
        text_provider=settings.text_provider,
        text_provider_external=True,  # all supported targets are external; local would flip this
        text_model=settings.text_api_model or None,
        nutrition_sources_configured=nutrition_configured,
    )


def capabilities(settings: Settings, nutrition: NutritionService) -> PlanCapabilities:
    return _capabilities(settings, nutrition.status().any_configured)


def _summary(p: MealPlan) -> PlanSummary:
    days = p.plan_json.get("days", [])
    return PlanSummary(
        id=p.id,
        title=p.title,
        week_start_date=p.week_start_date,
        source=p.source.value,
        status=p.status.value,
        revision=p.revision,
        day_count=len(days),
        meal_count=sum(len(d.get("meals", [])) for d in days),
        created_at=p.created_at,
        updated_at=p.updated_at,
    )


def _detail(p: MealPlan) -> PlanDetail:
    return PlanDetail(
        **_summary(p).model_dump(),
        notes=p.notes,
        plan=PlanOut.model_validate(p.plan_json),
        model_meta=p.model_meta,
        estimate=p.estimate_json,
        estimated_at=p.estimated_at,
    )


def _constraints_from_prefs(prefs) -> rules.Constraints:
    return rules.Constraints(
        dietary_pattern=(prefs.dietary_pattern or "omnivore"),
        allergies=tuple(prefs.allergies or ()),
        excluded_ingredients=tuple(prefs.excluded_ingredients or ()),
    )


def _to_day_dicts(days: list[DayOut]) -> list[dict[str, Any]]:
    return [d.model_dump(mode="json") for d in days]


def _coerce_input_days(body: PlanBody, week_start: date) -> list[DayOut]:
    end = week_start + timedelta(days=MAX_PLAN_DAYS - 1)
    for d in body.days:
        if not (week_start <= d.day_date <= end):
            raise InvalidPlanError(
                f"All entries must fall in {week_start.isoformat()}..{end.isoformat()}.",
            )
    return body.days


def _normalise_plan(body: PlanBody, week_start: date) -> PlanOut:
    days = _coerce_input_days(body, week_start)
    return PlanOut(days=days, notes=body.notes)


def create_blank(
    db: Session, user: User, req: CreateBlankPlanRequest
) -> PlanDetail:
    title = req.title or f"Week of {req.week_start_date.isoformat()}"
    week_days: list[DayOut] = [
        DayOut(
            day_date=req.week_start_date + timedelta(days=i),
            meals=[
                MealOut(
                    meal="breakfast",
                    title="",
                    servings=preferences_service.get_preferences(db, user).default_servings,
                    cooking_minutes=None,
                    ingredients=[],
                    notes=None,
                )
            ],
        )
        for i in range(MAX_PLAN_DAYS)
    ]
    plan = MealPlan(
        owner_id=user.id,
        title=title,
        week_start_date=req.week_start_date,
        source=MealPlanSource.MANUAL,
        status=MealPlanStatus.DRAFT,
        notes=None,
        plan_json=PlanOut(days=week_days).model_dump(mode="json"),
        revision=1,
    )
    repo.add(db, plan)
    db.commit()
    db.refresh(plan)
    logger.info("meal_plan_created user_id=%s plan_id=%s source=manual", user.id, plan.id)
    return _detail(plan)


def generate(
    db: Session,
    settings: Settings,
    user: User,
    req: GeneratePlanRequest,
    make_provider: Callable[[], TextProvider],
) -> PlanDetail:
    limiter(
        "meal plan generation", settings.meal_plan_generate_rate_limit_per_hour
    ).check(str(user.id))
    prefs = preferences_service.get_preferences(db, user)
    provider = make_provider()
    prompt = build_meal_plan_prompt(
        week_start=req.week_start_date,
        dietary_pattern=(prefs.dietary_pattern or "omnivore"),
        dietary_preferences=list(prefs.dietary_preferences or []),
        allergies=list(prefs.allergies or []),
        excluded_ingredients=list(prefs.excluded_ingredients or []),
        preferred_cuisines=list(prefs.preferred_cuisines or []),
        budget=(prefs.budget or "any"),
        max_cooking_minutes=prefs.max_cooking_minutes,
        default_servings=prefs.default_servings,
        pantry_ingredients=list(prefs.pantry_ingredients or []),
    )
    logger.info(
        "meal_plan_generate_start user_id=%s week=%s model=%s",
        user.id, req.week_start_date, provider.info.model,
    )
    raw = provider.complete_json(prompt, MEAL_PLAN_JSON_SCHEMA)
    parsed = parse_meal_plan_output(
        raw, week_start=req.week_start_date, default_servings=prefs.default_servings
    )
    days = [
        {
            "day_date": d.day_date.isoformat(),
            "meals": [
                {
                    "meal": m.meal,
                    "title": m.title,
                    "servings": m.servings,
                    "cooking_minutes": m.cooking_minutes,
                    "ingredients": [
                        {"name": i.name, "quantity": i.quantity, "unit": i.unit}
                        for i in m.ingredients
                    ],
                    "notes": m.notes,
                }
                for m in d.meals
                if req.include_snacks or m.meal != "snack"
            ],
        }
        for d in parsed.days
    ]
    # Reject early if a day became empty (only had snacks and user opted out).
    days = [d for d in days if d["meals"]]
    if not days:
        raise InvalidPlanError(
            "The model produced no meals after removing snacks, so its answer was discarded."
        )

    constraints = _constraints_from_prefs(prefs)
    violations = rules.find_violations(days=days, constraints=constraints)
    if violations:
        logger.info(
            "meal_plan_constraint_violation user_id=%s count=%d", user.id, len(violations)
        )
        raise ConstraintViolationError(violations)

    warnings = rules.soft_warnings(days=days, max_cooking_minutes=prefs.max_cooking_minutes)
    plan_out = PlanOut.model_validate({"days": days, "notes": parsed.notes})
    title = req.title or parsed.title or f"Week of {req.week_start_date.isoformat()}"

    plan = MealPlan(
        owner_id=user.id,
        title=title[:200],
        week_start_date=req.week_start_date,
        source=MealPlanSource.AI,
        status=MealPlanStatus.DRAFT,
        notes=req.notes or None,
        plan_json=plan_out.model_dump(mode="json"),
        model_meta={
            "provider": provider.info.model_dump(),
            "generated_at": datetime.now(UTC).isoformat(),
            "warnings": warnings.model_dump(mode="json"),
        },
        revision=1,
    )
    repo.add(db, plan)
    db.commit()
    db.refresh(plan)
    logger.info("meal_plan_generate_done user_id=%s plan_id=%s", user.id, plan.id)
    return _detail(plan)


def list_plans(db: Session, user: User, *, page: int, page_size: int) -> Page[PlanSummary]:
    rows, total = repo.list_page(
        db, user.id, limit=page_size, offset=(page - 1) * page_size
    )
    return Page.build([_summary(p) for p in rows], total, page, page_size)


def get_plan(db: Session, user: User, plan_id: uuid.UUID) -> PlanDetail:
    plan = repo.get_owned(db, plan_id, user.id)
    if plan is None:
        raise NotFoundError("Meal plan not found.", code="meal_plan_not_found")
    return _detail(plan)


def update_plan(db: Session, user: User, plan_id: uuid.UUID, body: PlanBody) -> PlanDetail:
    plan = repo.get_owned(db, plan_id, user.id)
    if plan is None:
        raise NotFoundError("Meal plan not found.", code="meal_plan_not_found")
    if body.expected_revision is not None and body.expected_revision != plan.revision:
        raise ConflictError(
            "This plan was changed somewhere else. Reload it and try again.",
            code="meal_plan_revision_conflict",
        )
    normalised = _normalise_plan(body, body.week_start_date)
    constraints = _constraints_from_prefs(preferences_service.get_preferences(db, user))
    violations = rules.find_violations(
        days=_to_day_dicts(normalised.days), constraints=constraints
    )
    if violations:
        raise ConstraintViolationError(violations)
    plan.title = body.title[:200]
    plan.week_start_date = body.week_start_date
    plan.notes = body.notes
    plan.plan_json = normalised.model_dump(mode="json")
    plan.revision += 1
    plan.estimate_json = None
    plan.estimated_at = None
    db.commit()
    db.refresh(plan)
    return _detail(plan)


def delete_plan(db: Session, user: User, plan_id: uuid.UUID) -> None:
    plan = repo.get_owned(db, plan_id, user.id)
    if plan is None:
        raise NotFoundError("Meal plan not found.", code="meal_plan_not_found")
    db.delete(plan)
    db.commit()
    logger.info("meal_plan_deleted user_id=%s plan_id=%s", user.id, plan_id)


def copy_plan(db: Session, user: User, plan_id: uuid.UUID, req: CopyPlanRequest) -> PlanDetail:
    source = repo.get_owned(db, plan_id, user.id)
    if source is None:
        raise NotFoundError("Meal plan not found.", code="meal_plan_not_found")
    shift = (req.week_start_date - source.week_start_date).days
    new_days: list[dict[str, Any]] = []
    for day in source.plan_json.get("days", []):
        new_date = (date.fromisoformat(day["day_date"]) + timedelta(days=shift)).isoformat()
        new_days.append({**day, "day_date": new_date})
    title = (req.title or f"Copy of {source.title}")[:200]
    plan = MealPlan(
        owner_id=user.id,
        title=title,
        week_start_date=req.week_start_date,
        source=MealPlanSource.COPIED,
        status=MealPlanStatus.DRAFT,
        notes=source.notes,
        plan_json={
            "schema_version": 1,
            "days": new_days,
            "notes": source.plan_json.get("notes"),
        },
        revision=1,
    )
    repo.add(db, plan)
    db.commit()
    db.refresh(plan)
    logger.info("meal_plan_copied user_id=%s new_id=%s", user.id, plan.id)
    return _detail(plan)


def estimate(
    db: Session,
    settings: Settings,
    nutrition: NutritionService,
    user: User,
    plan_id: uuid.UUID,
) -> PlanDetail:
    limiter(
        "meal plan estimate", settings.meal_plan_estimate_rate_limit_per_hour
    ).check(str(user.id))
    plan = repo.get_owned(db, plan_id, user.id)
    if plan is None:
        raise NotFoundError("Meal plan not found.", code="meal_plan_not_found")
    if not nutrition.status().any_configured:
        raise AppError(
            "No nutrition data source is configured, so values cannot be estimated. "
            "See the setup notes (USDA_FDC_API_KEY, OPEN_FOOD_FACTS_ENABLED, or import a "
            "reference table).",
            code="nutrition_not_configured",
            status_code=503,
        )
    plan.estimate_json = _compute_estimate(plan.plan_json, nutrition)
    plan.estimated_at = datetime.now(UTC)
    db.commit()
    db.refresh(plan)
    logger.info("meal_plan_estimated user_id=%s plan_id=%s", user.id, plan_id)
    return _detail(plan)


def _compute_estimate(plan_json: dict[str, Any], nutrition: NutritionService) -> dict[str, Any]:
    """Best-effort deterministic estimate from trusted sources. Mass units only."""
    cache: dict[str, Any] = {}

    def lookup(name: str):
        key = name.strip().lower()
        if key in cache:
            return cache[key]
        try:
            outcome = nutrition.search(key, limit=1)
            result = outcome.results[0] if outcome.results else None
        except Exception:  # noqa: BLE001 -- a source outage must not abort the estimate
            result = None
        cache[key] = result
        return result

    days_out: list[dict[str, Any]] = []
    missing_count = 0
    for day in plan_json.get("days", []):
        day_low = day_high = 0.0
        day_complete = True
        day_missing: list[str] = []
        meals_out: list[dict[str, Any]] = []
        for meal in day.get("meals", []):
            meal_low = meal_high = 0.0
            meal_missing: list[str] = []
            ingredient_est: list[dict[str, Any]] = []
            for ing in meal.get("ingredients", []):
                name = str(ing.get("name", ""))
                qty = float(ing.get("quantity", 0))
                unit = str(ing.get("unit", "")).lower()
                grams = _to_grams(qty, unit)
                if grams is None:
                    meal_missing.append(name)
                    missing_count += 1
                    continue
                candidate = lookup(name)
                kcal_per_100g = (candidate.per_100g or {}).get("energy_kcal") if candidate else None
                if kcal_per_100g is None:
                    meal_missing.append(name)
                    missing_count += 1
                    continue
                kcal = kcal_per_100g * grams / 100.0
                meal_low += kcal
                meal_high += kcal
                ingredient_est.append(
                    {
                        "name": name,
                        "quantity": qty,
                        "unit": unit,
                        "grams": round(grams, 2),
                        "matched_source": candidate.source,
                        "matched_name": candidate.name,
                        "kcal": round(kcal, 1),
                    }
                )
            complete = not meal_missing
            meals_out.append(
                {
                    "meal": meal.get("meal"),
                    "title": meal.get("title"),
                    "kcal_low": round(meal_low, 1),
                    "kcal_high": round(meal_high, 1),
                    "complete": complete,
                    "missing_ingredients": meal_missing,
                    "ingredient_estimates": ingredient_est,
                }
            )
            day_low += meal_low
            day_high += meal_high
            if not complete:
                day_complete = False
                day_missing.extend(meal_missing)
        days_out.append(
            {
                "day_date": day.get("day_date"),
                "kcal_low": round(day_low, 1),
                "kcal_high": round(day_high, 1),
                "complete": day_complete,
                "missing_ingredients": day_missing,
                "meals": meals_out,
            }
        )

    warnings: list[str] = []
    if missing_count > 0:
        warnings.append("some_ingredients_unestimated")
    return {
        "method": "best_effort_ingredient_lookup",
        "unit_basis": "per 100 g, as published by each source; kcal computed from mass only",
        "generated_at": datetime.now(UTC).isoformat(),
        "days": days_out,
        "warnings": warnings,
        "notes": (
            "Values are estimates. Ingredients that did not match a trusted source are listed "
            "as missing, not estimated. Volume units (cups, tbsp) are NOT converted to grams "
            "because density is food-specific."
        ),
    }


_MASS_TO_G = {"g": 1.0, "kg": 1000.0, "oz": 28.349523125, "lb": 453.59237}


def _to_grams(qty: float, unit: str) -> float | None:
    factor = _MASS_TO_G.get(unit)
    return qty * factor if factor is not None else None


def plan_ingredients(plan_json: dict[str, Any]) -> list[tuple[str, float, str]]:
    out: list[tuple[str, float, str]] = []
    for day in plan_json.get("days", []):
        for meal in day.get("meals", []):
            for ing in meal.get("ingredients", []):
                out.append(
                    (
                        str(ing.get("name", "")),
                        float(ing.get("quantity", 0)),
                        str(ing.get("unit", "")),
                    )
                )
    return out