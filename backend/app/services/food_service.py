"""Food workflow: scan a photo -> user confirms items -> deterministic nutrition calculation.

Trust boundaries, in order:
  1. The vision model only *names* candidate foods. Its output is schema-validated and signed.
  2. The user edits/confirms names and enters portions.
  3. Nutrient values come only from a trusted source record the user picked (signed server-side
     at search time); the browser can neither alter nor invent them.
  4. Totals are computed by app.domain.nutrition_calc. No model is involved.
"""

import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.ai.openai_vision import is_local_url
from app.ai.vision import VisionProvider, VisionProviderInfo
from app.core.config import Settings
from app.core.errors import AppError
from app.core.limits import limiter
from app.core.signed_refs import InvalidRefError, sign_ref, verify_ref
from app.domain import nutrition_calc as calc
from app.media.storage import StorageBackend, StorageError
from app.models import MediaKind, User
from app.nutrition.nutrients import NUTRIENT_BY_KEY, NUTRIENTS
from app.nutrition.service import NutritionService
from app.nutrition.types import FoodCandidate
from app.schemas.food import (
    CalculateRequest,
    CalculationOut,
    CandidateOut,
    FoodCapabilities,
    FoodItemInput,
    FoodSnapshot,
    ItemCalcOut,
    MealAudit,
    ModelObservations,
    NutrientValueOut,
    ObservedFood,
    PortionOut,
    RangePortion,
    ScanResponse,
    ServingsPortion,
    TotalOut,
    VisionCapability,
    WeightPortion,
)
from app.services import media_service

logger = logging.getLogger("app.food")
Origin = Literal["model", "model_edited", "user_added"]
MAX_SCAN_IMAGE_BYTES = 16 * 1024 * 1024


class InvalidPortionError(AppError):
    status_code = 422
    code = "invalid_portion"


class InvalidItemError(AppError):
    status_code = 422
    code = "invalid_item"


# --------------------------------------------------------------------------- capabilities
def vision_capability(settings: Settings) -> VisionCapability:
    """What is configured. This does not contact the model server (that can be slow)."""
    if settings.vision_provider == "openai_compatible":
        return VisionCapability(
            configured=True,
            provider="openai_compatible",
            model=settings.vision_api_model,
            external=not is_local_url(settings.vision_api_base_url),
        )
    if not settings.ollama_enabled:
        return VisionCapability(
            configured=False,
            provider="ollama",
            message="Photo recognition is not enabled on this server. You can add foods manually.",
        )
    if not settings.ollama_vision_model:
        return VisionCapability(
            configured=False,
            provider="ollama",
            message="No vision model is configured on this server. You can add foods manually.",
        )
    return VisionCapability(
        configured=True, provider="ollama", model=settings.ollama_vision_model, external=False
    )


def capabilities(settings: Settings, nutrition: NutritionService) -> FoodCapabilities:
    return FoodCapabilities(vision=vision_capability(settings), nutrition=nutrition.status())


def candidate_out(settings: Settings, user: User, candidate: FoodCandidate) -> CandidateOut:
    snapshot = FoodSnapshot.model_validate(candidate.model_dump())
    ref = sign_ref(settings, "food", user.id, snapshot.model_dump(mode="json"))
    return CandidateOut(**snapshot.model_dump(), food_ref=ref)


# --------------------------------------------------------------------------- scan
def scan(
    db: Session,
    storage: StorageBackend,
    settings: Settings,
    user: User,
    media_id: uuid.UUID,
    make_provider: Callable[[], VisionProvider],
) -> ScanResponse:
    limiter("photo analysis", settings.scan_rate_limit_per_minute).check(str(user.id))
    asset = media_service.get_owned_or_404(db, user, media_id)  # ownership first
    if asset.kind != MediaKind.IMAGE:
        raise InvalidItemError("Only images can be analysed.")
    provider = make_provider()  # raises a clear error if vision is not configured
    try:
        handle = storage.open(asset.storage_key)
    except StorageError:
        raise AppError(
            "The photo file is unavailable.", code="media_not_found", status_code=404
        ) from None
    with handle:
        image = handle.read(MAX_SCAN_IMAGE_BYTES + 1)
    if len(image) > MAX_SCAN_IMAGE_BYTES:
        raise InvalidItemError("That image is too large to analyse.")

    logger.info(
        "scan_started user_id=%s media_id=%s model=%s", user.id, asset.id, provider.info.model
    )
    result = provider.identify(image)  # any failure is a VisionError with a safe message
    items = [
        ObservedFood(
            observed_id=i,
            name=d.name,
            description=d.description,
            ambiguous=d.ambiguous,
            alternatives=d.alternatives,
        )
        for i, d in enumerate(result.items)
    ]
    generated_at = datetime.now(UTC)
    payload = {
        "media_id": str(asset.id),
        "provider": provider.info.model_dump(),
        "items": [i.model_dump() for i in items],
        "notes": result.notes,
        "generated_at": generated_at.isoformat(),
    }
    logger.info("scan_finished user_id=%s media_id=%s items=%d", user.id, asset.id, len(items))
    return ScanResponse(
        scan_ref=sign_ref(settings, "scan", user.id, payload),
        media_id=asset.id,
        provider=provider.info,
        items=items,
        notes=result.notes,
        generated_at=generated_at,
    )


def read_scan(settings: Settings, user: User, scan_ref: str) -> ModelObservations:
    payload = verify_ref(settings, "scan", user.id, scan_ref)
    try:
        return ModelObservations(
            provider=VisionProviderInfo.model_validate(payload["provider"]),
            media_id=uuid.UUID(payload["media_id"]),
            items=[ObservedFood.model_validate(i) for i in payload["items"]],
            notes=payload.get("notes"),
            generated_at=datetime.fromisoformat(payload["generated_at"]),
        )
    except (KeyError, ValueError, TypeError, ValidationError):
        raise InvalidRefError() from None


# --------------------------------------------------------------------------- calculation
@dataclass
class _Resolved:
    item_id: uuid.UUID
    name: str
    origin: Origin
    observed_name: str | None
    food: FoodSnapshot | None
    portion_input: WeightPortion | RangePortion | ServingsPortion | None


def _read_food_ref(settings: Settings, user: User, ref: str) -> FoodSnapshot:
    payload = verify_ref(settings, "food", user.id, ref)
    try:
        return FoodSnapshot.model_validate(payload)
    except ValidationError:
        raise InvalidRefError() from None


def _resolve(
    settings: Settings,
    user: User,
    items: list[FoodItemInput],
    observations: ModelObservations | None,
    existing: MealAudit | None,
) -> list[_Resolved]:
    existing_by_id = {i.item_id: i for i in existing.items} if existing else {}
    seen_ids: set[uuid.UUID] = set()
    resolved: list[_Resolved] = []
    for inp in items:
        base: ItemCalcOut | None = None
        if inp.item_id is not None and existing is not None:
            base = existing_by_id.get(inp.item_id)
            if base is None:
                raise InvalidItemError(f"'{inp.name}' does not belong to this meal.")
        item_id = inp.item_id or uuid.uuid4()
        if item_id in seen_ids:
            raise InvalidItemError("The same item was sent twice.")
        seen_ids.add(item_id)

        origin: Origin
        observed_name: str | None
        if base is not None:
            observed_name = base.observed_name
            origin = base.origin
            if origin == "model" and inp.name.casefold() != (observed_name or "").casefold():
                origin = "model_edited"
        elif inp.observed_id is not None:
            if observations is None:
                raise InvalidItemError("A scan reference is required for items from a photo.")
            if inp.observed_id >= len(observations.items):
                raise InvalidItemError("That detected item does not exist in the scan.")
            observed_name = observations.items[inp.observed_id].name
            origin = "model" if inp.name.casefold() == observed_name.casefold() else "model_edited"
        else:
            observed_name, origin = None, "user_added"

        food_changed = False
        food: FoodSnapshot | None
        if inp.food_ref:
            food = _read_food_ref(settings, user, inp.food_ref)
            food_changed = True
        elif inp.clear_food:
            food, food_changed = None, True
        else:
            food = base.food if base else None

        portion = inp.portion
        if portion is None and base is not None:
            portion = base.portion_input
            if food_changed and isinstance(portion, ServingsPortion):
                portion = None  # "servings" belonged to the old food's serving size
        resolved.append(_Resolved(item_id, inp.name, origin, observed_name, food, portion))
    return resolved


def _to_portion(item: _Resolved) -> calc.Portion | None:
    p = item.portion_input
    try:
        if p is None:
            return None
        if isinstance(p, WeightPortion):
            return calc.weight_portion(p.amount, p.unit)
        if isinstance(p, RangePortion):
            return calc.range_portion(p.min_amount, p.max_amount, p.unit)
        return calc.servings_portion(p.count, item.food.serving_grams if item.food else None)
    except calc.PortionError as exc:
        raise InvalidPortionError(f"{item.name}: {exc}") from None


def _f(value: Decimal) -> float:
    return float(calc.round_amount(value))


def _compute(resolved: list[_Resolved]) -> CalculationOut:
    results: list[calc.ItemResult] = []
    out_items: list[ItemCalcOut] = []
    for r in resolved:
        portion = _to_portion(r)
        result = calc.compute_item(
            calc.ItemInput(
                name=r.name, per_100g=r.food.per_100g if r.food else None, portion=portion
            )
        )
        results.append(result)
        out_items.append(
            ItemCalcOut(
                item_id=r.item_id,
                name=r.name,
                origin=r.origin,
                observed_name=r.observed_name,
                food=r.food,
                portion_input=r.portion_input,
                portion=PortionOut(
                    description=portion.description,
                    grams_low=_f(portion.grams_low),
                    grams_high=_f(portion.grams_high),
                    uncertain=portion.uncertain,
                )
                if portion
                else None,
                nutrients={
                    key: NutrientValueOut(low=_f(lo), high=_f(hi), unit=NUTRIENT_BY_KEY[key].unit)
                    for key, (lo, hi) in result.nutrients.items()
                },
                not_reported=list(result.not_reported),
                warnings=list(result.warnings),
            )
        )

    totals_raw = calc.compute_totals(results)
    totals = {
        key: TotalOut(
            key=key,
            label=NUTRIENT_BY_KEY[key].label,
            unit=NUTRIENT_BY_KEY[key].unit,
            low=_f(t.low) if t.low is not None else None,
            high=_f(t.high) if t.high is not None else None,
            complete=t.complete,
            contributing_items=t.contributing_items,
            missing_items=list(t.missing_items),
        )
        for key, t in totals_raw.items()
    }
    warnings: list[str] = []
    if any(not totals[n.key].complete for n in NUTRIENTS if n.core):
        warnings.append("incomplete_totals")
    if any(i.portion and i.portion.uncertain for i in out_items):
        warnings.append("estimated_portions")
    if all(not r.has_nutrition_data for r in results):
        warnings.append("no_nutrition_data")
    return CalculationOut(items=out_items, totals=totals, warnings=warnings)


def calculate_audit(
    settings: Settings,
    user: User,
    items: list[FoodItemInput],
    *,
    scan_ref: str | None,
    existing: MealAudit | None,
) -> MealAudit:
    observations = read_scan(settings, user, scan_ref) if scan_ref else None
    resolved = _resolve(settings, user, items, observations, existing)
    calculation = _compute(resolved)
    return MealAudit(
        **calculation.model_dump(),
        model_observations=observations or (existing.model_observations if existing else None),
    )


def calculate(
    db: Session,
    settings: Settings,
    user: User,
    request: CalculateRequest,
    load_existing: Callable[[Session, User, uuid.UUID], MealAudit],
) -> CalculationOut:
    existing = load_existing(db, user, request.meal_id) if request.meal_id else None
    audit = calculate_audit(
        settings, user, request.items, scan_ref=request.scan_ref, existing=existing
    )
    return CalculationOut.model_validate(
        audit.model_dump(exclude={"schema_version", "model_observations"})
    )


def audit_json(audit: MealAudit) -> dict[str, Any]:
    return audit.model_dump(mode="json")
