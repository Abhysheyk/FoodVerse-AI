import uuid
from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.ai.ollama import OllamaClient
from app.core.config import Settings, get_settings
from app.core.errors import ForbiddenError, NotAuthenticatedError
from app.core.security import decode_access_token
from app.db.session import get_db
from app.models import User
from app.repositories import users as user_repo

CSRF_HEADER = "X-Requested-With"
CSRF_VALUE = "FoodVerseWeb"

DbSession = Annotated[Session, Depends(get_db)]
AppSettings = Annotated[Settings, Depends(get_settings)]
_bearer = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    db: DbSession,
    settings: AppSettings,
) -> User:
    if credentials is None:
        raise NotAuthenticatedError()
    subject = decode_access_token(credentials.credentials, settings)
    if subject is None:
        raise NotAuthenticatedError("Invalid or expired token.", code="invalid_token")
    try:
        user_id = uuid.UUID(subject)
    except ValueError:
        raise NotAuthenticatedError("Invalid or expired token.", code="invalid_token") from None
    user = user_repo.get_by_id(db, user_id)
    if user is None or not user.is_active:
        raise NotAuthenticatedError("Invalid or expired token.", code="invalid_token")
    return user


def require_csrf_header(request: Request) -> None:
    """Cookie-authenticated endpoints must carry a custom header.

    Browsers cannot add a custom header cross-site without a CORS preflight, which our CORS
    allow-list rejects for foreign origins. Combined with SameSite cookies this blocks CSRF.
    """
    if request.headers.get(CSRF_HEADER) != CSRF_VALUE:
        raise ForbiddenError("Missing or invalid CSRF header.", code="csrf_check_failed")


def get_ollama_client(settings: AppSettings) -> OllamaClient:
    return OllamaClient(settings)


CurrentUser = Annotated[User, Depends(get_current_user)]
