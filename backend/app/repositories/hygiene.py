import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import AnalysisRecord, HygieneInspection


def list_page(
    db: Session,
    owner_id: uuid.UUID,
    *,
    limit: int,
    offset: int,
    status: str | None = None,
    location_type: str | None = None,
) -> tuple[list[tuple[HygieneInspection, AnalysisRecord]], int]:
    where = [HygieneInspection.owner_id == owner_id]
    if status is not None:
        where.append(HygieneInspection.status == status)
    if location_type is not None:
        where.append(HygieneInspection.location_type == location_type)
    total = db.scalar(select(func.count()).select_from(HygieneInspection).where(*where)) or 0
    rows = db.execute(
        select(HygieneInspection, AnalysisRecord)
        .join(AnalysisRecord, AnalysisRecord.id == HygieneInspection.analysis_id)
        .where(*where)
        .order_by(HygieneInspection.created_at.desc(), HygieneInspection.analysis_id)
        .limit(limit)
        .offset(offset)
    ).all()
    return [(h, r) for h, r in rows], total


def get_owned(
    db: Session, inspection_id: uuid.UUID, owner_id: uuid.UUID
) -> tuple[HygieneInspection, AnalysisRecord] | None:
    row = db.execute(
        select(HygieneInspection, AnalysisRecord)
        .join(AnalysisRecord, AnalysisRecord.id == HygieneInspection.analysis_id)
        .where(
            HygieneInspection.analysis_id == inspection_id,
            HygieneInspection.owner_id == owner_id,
        )
    ).first()
    return (row[0], row[1]) if row else None