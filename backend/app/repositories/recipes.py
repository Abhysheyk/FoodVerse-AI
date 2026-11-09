import uuid

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.cooking import Recipe, RecipeStatus


def add(db: Session, recipe: Recipe) -> Recipe:
    db.add(recipe)
    db.flush()
    return recipe


def get_owned(db: Session, recipe_id: uuid.UUID, owner_id: uuid.UUID) -> Recipe | None:
    """The owner filter is part of the query: another user's id simply does not exist here."""
    return db.scalar(
        select(Recipe).where(Recipe.id == recipe_id, Recipe.owner_id == owner_id)
    )


def _escape_like(term: str) -> str:
    return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def list_page(
    db: Session,
    owner_id: uuid.UUID,
    *,
    limit: int,
    offset: int,
    query: str | None = None,
    favorite: bool | None = None,
    saved_only: bool = True,
):
    where = [Recipe.owner_id == owner_id]
    if saved_only:
        where.append(Recipe.status == RecipeStatus.SAVED)
    if favorite is not None:
        where.append(Recipe.favorite.is_(favorite))
    if query:
        pattern = f"%{_escape_like(query)}%"
        where.append(
            or_(
                Recipe.title.ilike(pattern, escape="\\"),
                Recipe.description.ilike(pattern, escape="\\"),
            )
        )
    total = db.scalar(select(func.count()).select_from(Recipe).where(*where)) or 0
    rows = db.scalars(
        select(Recipe)
        .where(*where)
        .order_by(Recipe.favorite.desc(), Recipe.updated_at.desc(), Recipe.id)
        .limit(limit)
        .offset(offset)
    ).all()
    return list(rows), total


def for_conversation(db: Session, conversation_id: uuid.UUID) -> list[Recipe]:
    return list(
        db.scalars(
            select(Recipe)
            .where(Recipe.conversation_id == conversation_id)
            .order_by(Recipe.created_at)
        ).all()
    )