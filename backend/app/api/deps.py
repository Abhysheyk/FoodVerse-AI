import uuid
from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.ai.factory import build_vision_provider
from app.ai.ollama import OllamaClient
from app.ai.vision import VisionProvider
from app.core.config import Settings, get_settings
from app.core.errors import ForbiddenError, NotAuthenticatedError
from app.core.security import decode_access_token
from app.db.session import get_db
from app.media.storage import LocalStorage, StorageBackend
from app.models import User
from app.nutrition.service import NutritionService, build_nutrition_service
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


def get_storage(settings: AppSettings) -> StorageBackend:
    """The one place a storage backend is chosen. Swap in an object-storage adapter here."""
    return LocalStorage(settings.media_root)


Storage = Annotated[StorageBackend, Depends(get_storage)]
CurrentUser = Annotated[User, Depends(get_current_user)]


def get_nutrition_service(settings: AppSettings, db: DbSession) -> NutritionService:
    """Overridable in tests so no real network call is ever made."""
    return build_nutrition_service(settings, db)


def get_vision_factory(settings: AppSettings) -> Callable[[], VisionProvider]:
    """Returns a callable so the provider is only built (and can only fail) after the request
    has been authenticated, rate limited and the photo's ownership verified."""
    return lambda: build_vision_provider(settings)


Nutrition = Annotated[NutritionService, Depends(get_nutrition_service)]
VisionFactory = Annotated[Callable[[], VisionProvider], Depends(get_vision_factory)]
