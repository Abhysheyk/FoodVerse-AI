import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.cooking import CookingConversation, CookingMessage


def add(db: Session, conversation: CookingConversation) -> CookingConversation:
    db.add(conversation)
    db.flush()
    return conversation


def get_owned(
    db: Session, conversation_id: uuid.UUID, owner_id: uuid.UUID
) -> CookingConversation | None:
    return db.scalar(
        select(CookingConversation).where(
            CookingConversation.id == conversation_id,
            CookingConversation.owner_id == owner_id,
        )
    )


def list_page(db: Session, owner_id: uuid.UUID, *, limit: int, offset: int):
    base = select(CookingConversation).where(CookingConversation.owner_id == owner_id)
    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0
    rows = db.scalars(
        base.order_by(CookingConversation.updated_at.desc(), CookingConversation.id)
        .limit(limit)
        .offset(offset)
    ).all()
    return list(rows), total


def message_count(db: Session, conversation_id: uuid.UUID) -> int:
    return (
        db.scalar(
            select(func.count())
            .select_from(CookingMessage)
            .where(CookingMessage.conversation_id == conversation_id)
        )
        or 0
    )


def recent_messages(
    db: Session, conversation_id: uuid.UUID, limit: int
) -> list[CookingMessage]:
    rows = db.scalars(
        select(CookingMessage)
        .where(CookingMessage.conversation_id == conversation_id)
        .order_by(CookingMessage.position.desc())
        .limit(limit)
    ).all()
    return list(reversed(rows))


def all_messages(db: Session, conversation_id: uuid.UUID) -> list[CookingMessage]:
    return list(
        db.scalars(
            select(CookingMessage)
            .where(CookingMessage.conversation_id == conversation_id)
            .order_by(CookingMessage.position)
        ).all()
    )


def next_position(db: Session, conversation_id: uuid.UUID) -> int:
    current = db.scalar(
        select(func.max(CookingMessage.position)).where(
            CookingMessage.conversation_id == conversation_id
        )
    )
    return int(current or 0) + 1


def add_message(db: Session, message: CookingMessage) -> CookingMessage:
    db.add(message)
    db.flush()
    return message