import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import AnalysisRecord, ModuleKey


def list_page(
    db: Session,
    owner_id: uuid.UUID,
    *,
    module: ModuleKey | None,
    limit: int,
    offset: int,
) -> tuple[list[AnalysisRecord], int]:
    base = select(AnalysisRecord).where(AnalysisRecord.owner_id == owner_id)
    if module is not None:
        base = base.where(AnalysisRecord.module == module)
    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0
    rows = db.scalars(
        base.order_by(AnalysisRecord.created_at.desc(), AnalysisRecord.id)
        .limit(limit)
        .offset(offset)
    ).all()
    return list(rows), total


def get_owned(db: Session, record_id: uuid.UUID, owner_id: uuid.UUID) -> AnalysisRecord | None:
    return db.scalar(
        select(AnalysisRecord).where(
            AnalysisRecord.id == record_id, AnalysisRecord.owner_id == owner_id
        )
    )


def counts_by_module(db: Session, owner_id: uuid.UUID) -> dict[str, int]:
    rows = db.execute(
        select(AnalysisRecord.module, func.count())
        .where(AnalysisRecord.owner_id == owner_id)
        .group_by(AnalysisRecord.module)
    ).all()
    return {str(module.value): int(n) for module, n in rows}
