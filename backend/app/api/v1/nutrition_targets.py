from datetime import UTC, date, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, Response, status

from app.api.deps import CurrentUser, DbSession, require_csrf_header
from app.schemas.nutrition_target import NutritionTarget, NutritionTargetRead
from app.services import nutrition_target_service

router = APIRouter(prefix="/users/me/nutrition-target", tags=["users"])


@router.get("", response_model=NutritionTargetRead)
def get_target(user: CurrentUser, db: DbSession) -> NutritionTargetRead:
    target = nutrition_target_service.get_target(db, user)
    if target is None:
        return NutritionTargetRead()
    return NutritionTargetRead.model_validate(target.model_dump())


@router.put(
    "", response_model=NutritionTargetRead,
    dependencies=[Depends(require_csrf_header)],
)
def put_target(body: NutritionTarget, user: CurrentUser, db: DbSession) -> NutritionTargetRead:
    return NutritionTargetRead.model_validate(
        nutrition_target_service.set_target(db, user, body).model_dump()
    )


@router.delete(
    "", status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_csrf_header)],
)
def delete_target(user: CurrentUser, db: DbSession) -> Response:
    nutrition_target_service.clear_target(db, user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/tracking")
def tracking(
    user: CurrentUser, db: DbSession,
    date_from: date | None = None, date_to: date | None = None,
) -> dict[str, Any]:
    today = datetime.now(UTC).date()
    return nutrition_target_service.tracking(
        db, user,
        date_from=date_from or (today - timedelta(days=6)),
        date_to=date_to or today,
    )