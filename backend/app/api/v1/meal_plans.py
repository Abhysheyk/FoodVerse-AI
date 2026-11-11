import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status

from app.api.deps import (
    AppSettings, CurrentUser, DbSession, Nutrition, TextFactory, require_csrf_header,
)
from app.schemas.common import MAX_PAGE_SIZE, Page
from app.schemas.meal_plan import (
    CopyPlanRequest, CreateBlankPlanRequest, GeneratePlanRequest,
    PlanBody, PlanCapabilities, PlanDetail, PlanSummary,
)
from app.services import meal_plan_service

router = APIRouter(prefix="/meal-plans", tags=["meal-plans"])


@router.get("/capabilities", response_model=PlanCapabilities)
def capabilities(_user: CurrentUser, settings: AppSettings, nutrition: Nutrition) -> PlanCapabilities:
    return meal_plan_service.capabilities(settings, nutrition)


@router.post(
    "/generate", response_model=PlanDetail, status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_csrf_header)],
)
def generate(
    body: GeneratePlanRequest, user: CurrentUser, db: DbSession,
    settings: AppSettings, make_provider: TextFactory,
) -> PlanDetail:
    return meal_plan_service.generate(db, settings, user, body, make_provider)


@router.post(
    "/blank", response_model=PlanDetail, status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_csrf_header)],
)
def create_blank(body: CreateBlankPlanRequest, user: CurrentUser, db: DbSession) -> PlanDetail:
    return meal_plan_service.create_blank(db, user, body)


@router.get("", response_model=Page[PlanSummary])
def list_plans(
    user: CurrentUser, db: DbSession,
    page: Annotated[int, Query(ge=1, le=100_000)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = 10,
) -> Page[PlanSummary]:
    return meal_plan_service.list_plans(db, user, page=page, page_size=page_size)


@router.get("/{plan_id}", response_model=PlanDetail)
def get_plan(plan_id: uuid.UUID, user: CurrentUser, db: DbSession) -> PlanDetail:
    return meal_plan_service.get_plan(db, user, plan_id)


@router.put(
    "/{plan_id}", response_model=PlanDetail,
    dependencies=[Depends(require_csrf_header)],
)
def update_plan(
    plan_id: uuid.UUID, body: PlanBody, user: CurrentUser, db: DbSession,
) -> PlanDetail:
    return meal_plan_service.update_plan(db, user, plan_id, body)


@router.delete(
    "/{plan_id}", status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_csrf_header)],
)
def delete_plan(plan_id: uuid.UUID, user: CurrentUser, db: DbSession) -> Response:
    meal_plan_service.delete_plan(db, user, plan_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{plan_id}/copy", response_model=PlanDetail, status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_csrf_header)],
)
def copy_plan(
    plan_id: uuid.UUID, body: CopyPlanRequest, user: CurrentUser, db: DbSession,
) -> PlanDetail:
    return meal_plan_service.copy_plan(db, user, plan_id, body)


@router.post(
    "/{plan_id}/estimate", response_model=PlanDetail,
    dependencies=[Depends(require_csrf_header)],
)
def estimate(
    plan_id: uuid.UUID, user: CurrentUser, db: DbSession,
    settings: AppSettings, nutrition: Nutrition,
) -> PlanDetail:
    return meal_plan_service.estimate(db, settings, nutrition, user, plan_id)