from fastapi import APIRouter, Depends

from app.api.deps import CurrentUser, DbSession, require_csrf_header
from app.schemas.user import PreferencesRead, PreferencesUpdate, UserRead
from app.services import preferences_service

router = APIRouter(prefix="/users/me", tags=["users"])


@router.get("", response_model=UserRead)
def read_me(user: CurrentUser) -> UserRead:
    return UserRead.model_validate(user)


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
