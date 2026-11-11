"""Nutrition targets and tracking.

Targets are user-set; nothing is inferred from data. Tracking distinguishes consumed meals
(from the meal log) from planned meals (from plans, which are never treated as eaten).
"""

import uuid  # noqa: F401 -- reserved for future per-plan tracking
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from app.models import AnalysisRecord, MealLog, User
from app.schemas.nutrition_target import NutritionTarget
from app.services import preferences_service


def get_target(db: Session, user: User) -> NutritionTarget | None:
    prefs = preferences_service.get_preferences(db, user)
    raw = prefs.nutrition_targets
    if not raw:
        return None
    try:
        return NutritionTarget.model_validate(raw)
    except Exception:  # noqa: BLE001 -- corrupted stored value is treated as unset
        return None


def set_target(db: Session, user: User, target: NutritionTarget) -> NutritionTarget:
    prefs = preferences_service.get_preferences(db, user)
    prefs.nutrition_targets = target.model_dump(exclude_none=True)
    db.commit()
    db.refresh(prefs)
    return NutritionTarget.model_validate(prefs.nutrition_targets or {})


def clear_target(db: Session, user: User) -> None:
    prefs = preferences_service.get_preferences(db, user)
    prefs.nutrition_targets = None
    db.commit()


def _kcal(totals: dict[str, Any]) -> tuple[float | None, float | None, bool]:
    energy = totals.get("energy_kcal") or {}
    low = energy.get("low")
    high = energy.get("high")
    complete = bool(energy.get("complete", False))
    if not isinstance(low, (int, float)) or not isinstance(high, (int, float)):
        return None, None, False
    return float(low), float(high), complete


def tracking(
    db: Session, user: User, *, date_from: date, date_to: date
) -> dict[str, Any]:
    if date_to < date_from:
        date_from, date_to = date_to, date_from
    if (date_to - date_from).days > 90:
        date_to = date_from + timedelta(days=90)

    target = get_target(db, user)
    rows = db.execute(
        select(MealLog, AnalysisRecord)
        .join(AnalysisRecord, AnalysisRecord.id == MealLog.analysis_id)
        .where(
            and_(
                MealLog.owner_id == user.id,
                MealLog.eaten_at
                >= datetime.combine(date_from, datetime.min.time(), tzinfo=UTC),
                MealLog.eaten_at
                < datetime.combine(
                    date_to + timedelta(days=1), datetime.min.time(), tzinfo=UTC
                ),
            )
        )
    ).all()

    by_day: dict[date, dict[str, Any]] = {}
    current = date_from
    while current <= date_to:
        by_day[current] = {
            "date": current.isoformat(),
            "meals_logged": 0,
            "kcal_low": 0.0,
            "kcal_high": 0.0,
            "complete": True,
        }
        current += timedelta(days=1)

    for meal, record in rows:
        day = meal.eaten_at.date()
        if day not in by_day:
            continue
        bucket = by_day[day]
        bucket["meals_logged"] += 1
        totals = (record.result or {}).get("totals", {})
        low, high, complete = _kcal(totals)
        if low is None or high is None:
            bucket["complete"] = False
        else:
            bucket["kcal_low"] += low
            bucket["kcal_high"] += high
            if not complete:
                bucket["complete"] = False

    days = [by_day[d] for d in sorted(by_day.keys())]
    days_with_data = sum(1 for d in days if d["meals_logged"] > 0)
    return {
        "range": {"from": date_from.isoformat(), "to": date_to.isoformat()},
        "target": target.model_dump(exclude_none=True) if target else None,
        "target_kcal": target.calories_min if target and target.calories_min else None,
        "days": days,
        "days_with_data": days_with_data,
        "chart_available": days_with_data >= 3,
        "note": (
            "Only consumed meals are shown. Planned meals are never counted until they appear "
            "in your meal log."
        ),
    }