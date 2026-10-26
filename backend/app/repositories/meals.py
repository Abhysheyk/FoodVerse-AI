import uuid
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import AnalysisRecord, MealCategory, MealLog


def list_page(
    db: Session,
    owner_id: uuid.UUID,
    *,
    limit: int,
    offset: int,
    category: MealCategory | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
) -> tuple[list[tuple[MealLog, AnalysisRecord]], int]:
    where = [MealLog.owner_id == owner_id]
    if category is not None:
        where.append(MealLog.category == category)
    if date_from is not None:
        where.append(MealLog.eaten_at >= date_from)
    if date_to is not None:
        where.append(MealLog.eaten_at < date_to)
    total = db.scalar(select(func.count()).select_from(MealLog).where(*where)) or 0
    rows = db.execute(
        select(MealLog, AnalysisRecord)
        .join(AnalysisRecord, AnalysisRecord.id == MealLog.analysis_id)
        .where(*where)
        .order_by(MealLog.eaten_at.desc(), MealLog.analysis_id)
        .limit(limit)
        .offset(offset)
    ).all()
    return [(m, r) for m, r in rows], total


def get_owned(
    db: Session, meal_id: uuid.UUID, owner_id: uuid.UUID
) -> tuple[MealLog, AnalysisRecord] | None:
    row = db.execute(
        select(MealLog, AnalysisRecord)
        .join(AnalysisRecord, AnalysisRecord.id == MealLog.analysis_id)
        .where(MealLog.analysis_id == meal_id, MealLog.owner_id == owner_id)
    ).first()
    return (row[0], row[1]) if row else None
