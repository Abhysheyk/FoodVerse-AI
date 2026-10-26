import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import AppSettings, CurrentUser, DbSession, require_csrf_header
from app.models import MealCategory
from app.schemas.common import MAX_PAGE_SIZE, Page
from app.schemas.meal import MealDetail, MealSummary, MealWrite
from app.services import meal_service

router = APIRouter(prefix="/meals", tags=["meals"])


@router.post(
    "",
    response_model=MealDetail,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_csrf_header)],
)
def create_meal(
    body: MealWrite, user: CurrentUser, db: DbSession, settings: AppSettings
) -> MealDetail:
    return meal_service.create_meal(db, settings, user, body)


@router.get("", response_model=Page[MealSummary])
def list_meals(
    user: CurrentUser,
    db: DbSession,
    category: MealCategory | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    page: Annotated[int, Query(ge=1, le=100_000)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = 10,
) -> Page[MealSummary]:
    return meal_service.list_meals(
        db,
        user,
        page=page,
        page_size=page_size,
        category=category,
        date_from=date_from,
        date_to=date_to,
    )


@router.get("/{meal_id}", response_model=MealDetail)
def get_meal(meal_id: uuid.UUID, user: CurrentUser, db: DbSession) -> MealDetail:
    return meal_service.get_meal(db, user, meal_id)


@router.put("/{meal_id}", response_model=MealDetail, dependencies=[Depends(require_csrf_header)])
def update_meal(
    meal_id: uuid.UUID, body: MealWrite, user: CurrentUser, db: DbSession, settings: AppSettings
) -> MealDetail:
    return meal_service.update_meal(db, settings, user, meal_id, body)


@router.delete(
    "/{meal_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_csrf_header)],
)
def delete_meal(meal_id: uuid.UUID, user: CurrentUser, db: DbSession) -> None:
    meal_service.delete_meal(db, user, meal_id)
