import uuid
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models import RefreshToken


def add(db: Session, *, user_id: uuid.UUID, token_hash: str, expires_at: datetime) -> RefreshToken:
    row = RefreshToken(user_id=user_id, token_hash=token_hash, expires_at=expires_at)
    db.add(row)
    db.flush()
    return row


def get_for_update(db: Session, token_hash: str) -> RefreshToken | None:
    """Row-locks the token so concurrent refreshes with the same token are serialised."""
    return db.scalar(
        select(RefreshToken).where(RefreshToken.token_hash == token_hash).with_for_update()
    )


def revoke_all_for_user(db: Session, user_id: uuid.UUID, now: datetime) -> None:
    db.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=now)
    )
