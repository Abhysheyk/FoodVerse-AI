import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.models import GroceryList


def add(db: Session, gl: GroceryList) -> GroceryList:
    db.add(gl)
    db.flush()
    return gl


def get_owned(db: Session, list_id: uuid.UUID, owner_id: uuid.UUID) -> GroceryList | None:
    return db.scalar(
        select(GroceryList)
        .options(selectinload(GroceryList.items))
        .where(GroceryList.id == list_id, GroceryList.owner_id == owner_id)
    )


def list_page(
    db: Session, owner_id: uuid.UUID, *, limit: int, offset: int
) -> tuple[list[GroceryList], int]:
    base = select(GroceryList).where(GroceryList.owner_id == owner_id)
    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0
    rows = db.scalars(
        base.options(selectinload(GroceryList.items))
        .order_by(GroceryList.created_at.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    return list(rows), total