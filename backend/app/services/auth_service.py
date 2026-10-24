"""Registration, login, refresh-token rotation and logout.

Refresh tokens are single-use. Presenting an already-used (revoked) token is treated as
possible theft: every session of that user is revoked. See docs/adr/0001-auth-session-strategy.md.
"""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core import security
from app.core.config import Settings
from app.core.errors import AppError, ConflictError, InvalidCredentialsError, NotAuthenticatedError
from app.models import User
from app.repositories import tokens as token_repo
from app.repositories import users as user_repo
from app.schemas.auth import LoginRequest, RegisterRequest

logger = logging.getLogger("app.auth")


@dataclass(frozen=True)
class AuthResult:
    user: User
    access_token: str
    expires_in: int
    refresh_token: str
    refresh_max_age: int


def _now() -> datetime:
    return datetime.now(UTC)


def _issue_tokens(db: Session, settings: Settings, user: User) -> AuthResult:
    access_token, expires_in = security.create_access_token(str(user.id), settings)
    raw_refresh = security.generate_refresh_token()
    max_age = settings.refresh_token_expire_days * 86400
    token_repo.add(
        db,
        user_id=user.id,
        token_hash=security.hash_refresh_token(raw_refresh),
        expires_at=_now() + timedelta(seconds=max_age),
    )
    return AuthResult(user, access_token, expires_in, raw_refresh, max_age)


def register(db: Session, settings: Settings, data: RegisterRequest) -> AuthResult:
    email = data.email.strip().lower()
    if user_repo.get_by_email(db, email) is not None:
        raise ConflictError("An account with this email already exists.", code="email_taken")
    try:
        user = user_repo.create_user(
            db,
            email=email,
            password_hash=security.hash_password(data.password),
            display_name=data.display_name,
        )
    except IntegrityError:  # lost a race with a concurrent registration
        db.rollback()
        raise ConflictError(
            "An account with this email already exists.", code="email_taken"
        ) from None
    result = _issue_tokens(db, settings, user)
    db.commit()
    logger.info("user_registered user_id=%s", user.id)
    return result


def login(db: Session, settings: Settings, data: LoginRequest) -> AuthResult:
    email = data.email.strip().lower()
    user = user_repo.get_by_email(db, email)
    if user is None:
        security.verify_dummy_password(data.password)
        raise InvalidCredentialsError("Incorrect email or password.")
    if not security.verify_password(user.password_hash, data.password) or not user.is_active:
        logger.info("login_failed user_id=%s", user.id)
        raise InvalidCredentialsError("Incorrect email or password.")
    if security.password_needs_rehash(user.password_hash):
        user.password_hash = security.hash_password(data.password)
    result = _issue_tokens(db, settings, user)
    db.commit()
    logger.info("login_succeeded user_id=%s", user.id)
    return result


def refresh(db: Session, settings: Settings, raw_token: str | None) -> AuthResult:
    invalid = NotAuthenticatedError(
        "Session expired. Please sign in again.", code="invalid_refresh"
    )
    if not raw_token:
        raise invalid
    now = _now()
    row = token_repo.get_for_update(db, security.hash_refresh_token(raw_token))
    if row is None:
        raise invalid
    if row.revoked_at is not None:
        token_repo.revoke_all_for_user(db, row.user_id, now)
        db.commit()
        logger.warning("refresh_token_reuse_detected user_id=%s", row.user_id)
        raise invalid
    if row.expires_at <= now:
        raise invalid
    user = user_repo.get_by_id(db, row.user_id)
    if user is None or not user.is_active:
        raise invalid
    row.revoked_at = now
    result = _issue_tokens(db, settings, user)
    db.commit()
    return result


def logout(db: Session, raw_token: str | None) -> None:
    """Revoke the presented refresh token. Always succeeds from the caller's point of view."""
    if not raw_token:
        return
    row = token_repo.get_for_update(db, security.hash_refresh_token(raw_token))
    if row is not None and row.revoked_at is None:
        row.revoked_at = _now()
        db.commit()
        logger.info("logout user_id=%s", row.user_id)
    else:
        db.rollback()


__all__ = ["AppError", "AuthResult", "login", "logout", "refresh", "register"]
