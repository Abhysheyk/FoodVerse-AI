"""Grocery lists: derived from a plan, then freely editable. Nothing is deleted implicitly."""

import logging
import uuid

from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError
from app.domain.grocery import merge_ingredients
from app.models import GroceryItem, GroceryList, User
from app.repositories import grocery as repo
from app.repositories import meal_plans as plan_repo
from app.schemas.common import Page
from app.schemas.grocery import (
    GroceryItemOut,
    GroceryListCreate,
    GroceryListDetail,
    GroceryListSummary,
    GroceryListUpdate,
)
from app.services import meal_plan_service

logger = logging.getLogger("app.grocery")


def _summary(gl: GroceryList) -> GroceryListSummary:
    items = list(gl.items)
    return GroceryListSummary(
        id=gl.id,
        title=gl.title,
        plan_id=gl.plan_id,
        revision=gl.revision,
        item_count=len(items),
        checked_count=sum(1 for i in items if i.checked),
        created_at=gl.created_at,
        updated_at=gl.updated_at,
    )


def _detail(gl: GroceryList) -> GroceryListDetail:
    items = sorted(gl.items, key=lambda i: (i.position, str(i.id)))
    return GroceryListDetail(
        **_summary(gl).model_dump(),
        items=[GroceryItemOut.model_validate(i) for i in items],
    )


def _get_or_404(db: Session, user: User, list_id: uuid.UUID) -> GroceryList:
    gl = repo.get_owned(db, list_id, user.id)
    if gl is None:
        raise NotFoundError("Grocery list not found.", code="grocery_list_not_found")
    return gl


def create_from_plan(db: Session, user: User, req: GroceryListCreate) -> GroceryListDetail:
    plan = plan_repo.get_owned(db, req.plan_id, user.id)
    if plan is None:
        raise NotFoundError("Meal plan not found.", code="meal_plan_not_found")
    lines = meal_plan_service.plan_ingredients(plan.plan_json)
    if not lines:
        raise NotFoundError(
            "This plan has no ingredients, so there is nothing to buy.",
            code="meal_plan_empty",
        )
    merged = merge_ingredients(lines)
    title = req.title or f"Groceries for {plan.title}"[:200]
    gl = GroceryList(owner_id=user.id, plan_id=plan.id, title=title, revision=1)
    for idx, row in enumerate(merged):
        gl.items.append(
            GroceryItem(
                name=str(row["name"])[:200],
                quantity=float(row["quantity"]),
                unit=str(row["unit"])[:16],
                checked=False,
                position=idx,
            )
        )
    repo.add(db, gl)
    db.commit()
    db.refresh(gl)
    logger.info(
        "grocery_list_created user_id=%s list_id=%s items=%d",
        user.id, gl.id, len(merged),
    )
    return _detail(gl)


def list_lists(
    db: Session, user: User, *, page: int, page_size: int
) -> Page[GroceryListSummary]:
    rows, total = repo.list_page(db, user.id, limit=page_size, offset=(page - 1) * page_size)
    return Page.build([_summary(r) for r in rows], total, page, page_size)


def get_list(db: Session, user: User, list_id: uuid.UUID) -> GroceryListDetail:
    return _detail(_get_or_404(db, user, list_id))


def update_list(
    db: Session, user: User, list_id: uuid.UUID, body: GroceryListUpdate
) -> GroceryListDetail:
    gl = _get_or_404(db, user, list_id)
    if body.expected_revision is not None and body.expected_revision != gl.revision:
        raise ConflictError(
            "This list was changed somewhere else. Reload it and try again.",
            code="grocery_list_revision_conflict",
        )
    gl.title = body.title[:200]
    gl.revision += 1
    gl.items.clear()
    db.flush()
    for idx, item in enumerate(body.items):
        gl.items.append(
            GroceryItem(
                list_id=gl.id,
                name=item.name[:200],
                quantity=item.quantity,
                unit=item.unit[:16],
                checked=item.checked,
                position=idx,
                notes=item.notes,
            )
        )
    db.commit()
    db.refresh(gl)
    return _detail(gl)


def delete_list(db: Session, user: User, list_id: uuid.UUID) -> None:
    gl = _get_or_404(db, user, list_id)
    db.delete(gl)
    db.commit()
    logger.info("grocery_list_deleted user_id=%s list_id=%s", user.id, list_id)