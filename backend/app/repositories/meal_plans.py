import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import MealPlan


def add(db: Session, plan: MealPlan) -> MealPlan:
    db.add(plan)
    db.flush()
    return plan


def get_owned(db: Session, plan_id: uuid.UUID, owner_id: uuid.UUID) -> MealPlan | None:
    return db.scalar(select(MealPlan).where(MealPlan.id == plan_id, MealPlan.owner_id == owner_id))


def list_page(
    db: Session, owner_id: uuid.UUID, *, limit: int, offset: int
) -> tuple[list[MealPlan], int]:
    base = select(MealPlan).where(MealPlan.owner_id == owner_id)
    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0
    rows = db.scalars(
        base.order_by(MealPlan.week_start_date.desc(), MealPlan.created_at.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    return list(rows), total