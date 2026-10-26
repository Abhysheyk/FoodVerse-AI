"""Saved meals. A meal is an AnalysisRecord (full audit JSON) plus a MealLog row (queryable
facts). Totals are always recomputed server-side from the confirmed items; the client never
supplies a number that is stored."""

import logging
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import AppError, ConflictError, NotFoundError
from app.models import (
    AnalysisRecord,
    AnalysisStatus,
    MealCategory,
    MealLog,
    MediaKind,
    ModuleKey,
    User,
)
from app.repositories import meals as meal_repo
from app.schemas.common import Page
from app.schemas.food import MealAudit
from app.schemas.meal import BriefTotal, MealDetail, MealSummary, MealWrite
from app.services import food_service, media_service

logger = logging.getLogger("app.meals")


def _get_or_404(db: Session, user: User, meal_id: uuid.UUID) -> tuple[MealLog, AnalysisRecord]:
    found = meal_repo.get_owned(db, meal_id, user.id)
    if found is None:  # same answer for "missing" and "someone else's"
        raise NotFoundError("Meal not found.", code="meal_not_found")
    return found


def load_audit(db: Session, user: User, meal_id: uuid.UUID) -> MealAudit:
    _, record = _get_or_404(db, user, meal_id)
    return MealAudit.model_validate(record.result)


def _brief(totals: dict[str, Any]) -> BriefTotal:
    energy = totals.get("energy_kcal") or {}
    return BriefTotal(
        low=energy.get("low"), high=energy.get("high"), complete=bool(energy.get("complete", False))
    )


def _summary(meal: MealLog, record: AnalysisRecord) -> MealSummary:
    return MealSummary(
        id=meal.analysis_id,
        title=record.title,
        items_label=meal.items_label,
        category=meal.category,
        eaten_at=meal.eaten_at,
        item_count=meal.item_count,
        calories=_brief(meal.totals),
        media_id=record.media_id,
        revision=meal.revision,
        created_at=record.created_at,
        updated_at=meal.updated_at,
    )


def _detail(meal: MealLog, record: AnalysisRecord) -> MealDetail:
    return MealDetail(
        **_summary(meal, record).model_dump(),
        notes=meal.notes,
        result=MealAudit.model_validate(record.result),
    )


def _summary_text(audit: MealAudit) -> str:
    energy = audit.totals["energy_kcal"]
    n = len(audit.items)
    items = f"{n} item{'s' if n != 1 else ''}"
    if energy.low is None or energy.high is None:
        return f"{items} · calories unavailable"
    if energy.low == energy.high:
        kcal = f"{energy.low:g} kcal"
    else:
        kcal = f"{energy.low:g}–{energy.high:g} kcal"
    return f"{items} · {kcal}" + ("" if energy.complete else " (incomplete)")


def _prepare(
    db: Session,
    settings: Settings,
    user: User,
    data: MealWrite,
    existing: MealAudit | None,
) -> tuple[MealAudit, uuid.UUID | None]:
    audit = food_service.calculate_audit(
        settings, user, data.items, scan_ref=data.scan_ref, existing=existing
    )
    media_id = data.media_id
    if media_id is None and audit.model_observations is not None:
        media_id = audit.model_observations.media_id
    if media_id is not None:
        asset = media_service.get_owned_or_404(db, user, media_id)  # must be the user's own
        if asset.kind != MediaKind.IMAGE:
            raise AppError(
                "Only an image can be attached to a meal.", code="invalid_item", status_code=422
            )
    return audit, media_id


def _labels(audit: MealAudit, category: MealCategory) -> tuple[str, str]:
    label = ", ".join(i.name for i in audit.items)
    if len(label) > 200:
        label = label[:197] + "…"
    return label, f"{category.value.capitalize()}: {label}"[:200]


def create_meal(db: Session, settings: Settings, user: User, data: MealWrite) -> MealDetail:
    audit, media_id = _prepare(db, settings, user, data, existing=None)
    items_label, title = _labels(audit, data.category)
    record = AnalysisRecord(
        owner_id=user.id,
        module=ModuleKey.FOOD_RECOGNITION,
        status=AnalysisStatus.COMPLETED,
        title=title,
        summary=_summary_text(audit),
        result=food_service.audit_json(audit),
        media_id=media_id,
    )
    db.add(record)
    db.flush()
    meal = MealLog(
        analysis_id=record.id,
        owner_id=user.id,
        eaten_at=data.eaten_at,
        category=data.category,
        notes=data.notes,
        totals={k: v.model_dump(mode="json") for k, v in audit.totals.items()},
        item_count=len(audit.items),
        revision=1,
        items_label=items_label,
    )
    db.add(meal)
    db.commit()
    db.refresh(record)
    db.refresh(meal)
    logger.info("meal_created user_id=%s meal_id=%s items=%d", user.id, record.id, len(audit.items))
    return _detail(meal, record)


def update_meal(
    db: Session, settings: Settings, user: User, meal_id: uuid.UUID, data: MealWrite
) -> MealDetail:
    meal, record = _get_or_404(db, user, meal_id)
    if data.expected_revision is not None and data.expected_revision != meal.revision:
        raise ConflictError(
            "This meal was changed somewhere else. Reload it and try again.",
            code="meal_revision_conflict",
        )
    existing = MealAudit.model_validate(record.result)
    audit, media_id = _prepare(db, settings, user, data, existing=existing)
    items_label, title = _labels(audit, data.category)

    record.title = title
    record.summary = _summary_text(audit)
    record.result = food_service.audit_json(audit)
    record.media_id = media_id
    meal.eaten_at = data.eaten_at
    meal.category = data.category
    meal.notes = data.notes
    meal.totals = {k: v.model_dump(mode="json") for k, v in audit.totals.items()}
    meal.item_count = len(audit.items)
    meal.items_label = items_label
    meal.revision += 1
    db.commit()
    db.refresh(record)
    db.refresh(meal)
    logger.info("meal_updated user_id=%s meal_id=%s revision=%d", user.id, meal_id, meal.revision)
    return _detail(meal, record)


def get_meal(db: Session, user: User, meal_id: uuid.UUID) -> MealDetail:
    meal, record = _get_or_404(db, user, meal_id)
    return _detail(meal, record)


def delete_meal(db: Session, user: User, meal_id: uuid.UUID) -> None:
    _, record = _get_or_404(db, user, meal_id)
    db.delete(record)  # meal_logs row goes with it (ON DELETE CASCADE)
    db.commit()
    logger.info("meal_deleted user_id=%s meal_id=%s", user.id, meal_id)


def list_meals(
    db: Session,
    user: User,
    *,
    page: int,
    page_size: int,
    category: MealCategory | None,
    date_from: datetime | None,
    date_to: datetime | None,
) -> Page[MealSummary]:
    if date_from and date_to and date_from >= date_to:
        raise AppError("date_from must be before date_to.", code="invalid_range", status_code=422)
    rows, total = meal_repo.list_page(
        db,
        user.id,
        limit=page_size,
        offset=(page - 1) * page_size,
        category=category,
        date_from=date_from,
        date_to=date_to,
    )
    return Page.build([_summary(m, r) for m, r in rows], total, page, page_size)
