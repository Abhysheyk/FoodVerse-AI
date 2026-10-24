from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, Response, status

from app.api.deps import AppSettings, DbSession, require_csrf_header
from app.core.config import Settings
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse
from app.schemas.user import UserRead
from app.services import auth_service
from app.services.auth_service import AuthResult

REFRESH_COOKIE = "fv_refresh"
# The cookie is only ever sent to the auth endpoints, never to data endpoints.
REFRESH_COOKIE_PATH = "/api/v1/auth"

router = APIRouter(prefix="/auth", tags=["auth"])


def _set_refresh_cookie(response: Response, token: str, max_age: int, settings: Settings) -> None:
    response.set_cookie(
        REFRESH_COOKIE,
        token,
        max_age=max_age,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        path=REFRESH_COOKIE_PATH,
    )


def _clear_refresh_cookie(response: Response, settings: Settings) -> None:
    response.delete_cookie(
        REFRESH_COOKIE,
        path=REFRESH_COOKIE_PATH,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
    )


def _respond(result: AuthResult, response: Response, settings: Settings) -> TokenResponse:
    _set_refresh_cookie(response, result.refresh_token, result.refresh_max_age, settings)
    return TokenResponse(
        access_token=result.access_token,
        expires_in=result.expires_in,
        user=UserRead.model_validate(result.user),
    )


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register(
    body: RegisterRequest, response: Response, db: DbSession, settings: AppSettings
) -> TokenResponse:
    return _respond(auth_service.register(db, settings, body), response, settings)


@router.post("/login", response_model=TokenResponse)
def login(
    body: LoginRequest, response: Response, db: DbSession, settings: AppSettings
) -> TokenResponse:
    return _respond(auth_service.login(db, settings, body), response, settings)


@router.post("/refresh", response_model=TokenResponse, dependencies=[Depends(require_csrf_header)])
def refresh(
    response: Response,
    db: DbSession,
    settings: AppSettings,
    refresh_token: Annotated[str | None, Cookie(alias=REFRESH_COOKIE)] = None,
) -> TokenResponse:
    try:
        result = auth_service.refresh(db, settings, refresh_token)
    except Exception:
        # A failed refresh must not leave a stale cookie behind in the browser.
        _clear_refresh_cookie(response, settings)
        raise
    return _respond(result, response, settings)


@router.post(
    "/logout", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_csrf_header)]
)
def logout(
    response: Response,
    db: DbSession,
    settings: AppSettings,
    refresh_token: Annotated[str | None, Cookie(alias=REFRESH_COOKIE)] = None,
) -> None:
    auth_service.logout(db, refresh_token)
    _clear_refresh_cookie(response, settings)
