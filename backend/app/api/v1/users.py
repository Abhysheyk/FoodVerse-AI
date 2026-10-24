from fastapi import APIRouter, Depends, Response, status

from app.api.deps import CurrentUser, DbSession, require_csrf_header
from app.schemas.user import (
    PasswordChange,
    PreferencesRead,
    PreferencesUpdate,
    ProfileUpdate,
    UserRead,
)
from app.services import account_service, preferences_service

router = APIRouter(prefix="/users/me", tags=["users"])


@router.get("", response_model=UserRead)
def read_me(user: CurrentUser) -> UserRead:
    return UserRead.model_validate(user)


@router.patch("", response_model=UserRead, dependencies=[Depends(require_csrf_header)])
def update_me(body: ProfileUpdate, user: CurrentUser, db: DbSession) -> UserRead:
    return UserRead.model_validate(account_service.update_profile(db, user, body))


@router.post(
    "/password",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_csrf_header)],
)
def change_password(body: PasswordChange, user: CurrentUser, db: DbSession) -> Response:
    account_service.change_password(db, user, body)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/preferences", response_model=PreferencesRead)
def read_preferences(user: CurrentUser, db: DbSession) -> PreferencesRead:
    return PreferencesRead.model_validate(preferences_service.get_preferences(db, user))


@router.put(
    "/preferences",
    response_model=PreferencesRead,
    dependencies=[Depends(require_csrf_header)],
)
def update_preferences(
    body: PreferencesUpdate, user: CurrentUser, db: DbSession
) -> PreferencesRead:
    return PreferencesRead.model_validate(preferences_service.update_preferences(db, user, body))
