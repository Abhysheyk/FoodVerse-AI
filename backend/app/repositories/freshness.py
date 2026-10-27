import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import AnalysisRecord, FreshnessAssessment


def list_page(
    db: Session,
    owner_id: uuid.UUID,
    *,
    limit: int,
    offset: int,
    label: str | None = None,
    category: str | None = None,
) -> tuple[list[tuple[FreshnessAssessment, AnalysisRecord]], int]:
    where = [FreshnessAssessment.owner_id == owner_id]
    if label is not None:
        where.append(FreshnessAssessment.label == label)
    if category is not None:
        where.append(FreshnessAssessment.food_category == category)
    total = db.scalar(select(func.count()).select_from(FreshnessAssessment).where(*where)) or 0
    rows = db.execute(
        select(FreshnessAssessment, AnalysisRecord)
        .join(AnalysisRecord, AnalysisRecord.id == FreshnessAssessment.analysis_id)
        .where(*where)
        .order_by(FreshnessAssessment.created_at.desc(), FreshnessAssessment.analysis_id)
        .limit(limit)
        .offset(offset)
    ).all()
    return [(a, r) for a, r in rows], total


def get_owned(
    db: Session, assessment_id: uuid.UUID, owner_id: uuid.UUID
) -> tuple[FreshnessAssessment, AnalysisRecord] | None:
    row = db.execute(
        select(FreshnessAssessment, AnalysisRecord)
        .join(AnalysisRecord, AnalysisRecord.id == FreshnessAssessment.analysis_id)
        .where(
            FreshnessAssessment.analysis_id == assessment_id,
            FreshnessAssessment.owner_id == owner_id,
        )
    ).first()
    return (row[0], row[1]) if row else None
