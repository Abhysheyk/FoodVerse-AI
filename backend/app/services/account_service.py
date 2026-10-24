import logging
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.core import security
from app.core.errors import AppError
from app.models import User
from app.repositories import tokens as token_repo
from app.schemas.user import PasswordChange, ProfileUpdate

logger = logging.getLogger("app.account")


def update_profile(db: Session, user: User, data: ProfileUpdate) -> User:
    user.display_name = data.display_name
    db.commit()
    db.refresh(user)
    return user


def change_password(db: Session, user: User, data: PasswordChange) -> None:
    # 400, not 401: the frontend treats 401 as "session lost", which this is not.
    if not security.verify_password(user.password_hash, data.current_password):
        raise AppError("Current password is incorrect.", code="invalid_current_password")
    if data.new_password == data.current_password:
        raise AppError("Choose a different password.", code="password_unchanged")
    user.password_hash = security.hash_password(data.new_password)
    # Sign out everywhere: every refresh token is revoked. Existing access tokens expire on
    # their own (max 15 minutes), as documented in ADR 0001.
    token_repo.revoke_all_for_user(db, user.id, datetime.now(UTC))
    db.commit()
    logger.info("password_changed user_id=%s", user.id)
