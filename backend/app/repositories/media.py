import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import MediaAsset


def add(db: Session, asset: MediaAsset) -> MediaAsset:
    db.add(asset)
    db.flush()
    return asset


def get_owned(db: Session, asset_id: uuid.UUID, owner_id: uuid.UUID) -> MediaAsset | None:
    """The owner filter is part of the query: another user's id simply does not exist here."""
    return db.scalar(
        select(MediaAsset).where(MediaAsset.id == asset_id, MediaAsset.owner_id == owner_id)
    )


def list_page(
    db: Session, owner_id: uuid.UUID, *, limit: int, offset: int
) -> tuple[list[MediaAsset], int]:
    base = select(MediaAsset).where(MediaAsset.owner_id == owner_id)
    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0
    rows = db.scalars(
        base.order_by(MediaAsset.created_at.desc(), MediaAsset.id).limit(limit).offset(offset)
    ).all()
    return list(rows), total


def usage(db: Session, owner_id: uuid.UUID) -> tuple[int, int]:
    """(count, total_bytes) for one owner."""
    row = db.execute(
        select(func.count(MediaAsset.id), func.coalesce(func.sum(MediaAsset.size_bytes), 0)).where(
            MediaAsset.owner_id == owner_id
        )
    ).one()
    return int(row[0]), int(row[1])
