import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status

from app.api.deps import (
    AppSettings,
    CurrentUser,
    DbSession,
    Storage,
    VisionFactory,
    require_csrf_header,
)
from app.domain.freshness import FoodCategory, VisualLabel
from app.schemas.common import MAX_PAGE_SIZE, Page
from app.schemas.freshness import (
    AssessmentRequest,
    FreshnessCapabilities,
    FreshnessDetail,
    FreshnessSummary,
)
from app.services import freshness_service

router = APIRouter(prefix="/freshness", tags=["freshness"])


@router.get("/capabilities", response_model=FreshnessCapabilities)
def capabilities(_user: CurrentUser, settings: AppSettings) -> FreshnessCapabilities:
    """Form choices, and whether photo analysis is configured on this server."""
    return freshness_service.capabilities(settings)


@router.post(
    "/assessments",
    response_model=FreshnessDetail,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_csrf_header)],
)
def create_assessment(
    body: AssessmentRequest,
    user: CurrentUser,
    db: DbSession,
    storage: Storage,
    settings: AppSettings,
    make_provider: VisionFactory,
) -> FreshnessDetail:
    """Analyse one of the user's own photos (or give guidance only) and save the result."""
    return freshness_service.create_assessment(db, storage, settings, user, body, make_provider)


@router.get("/assessments", response_model=Page[FreshnessSummary])
def list_assessments(
    user: CurrentUser,
    db: DbSession,
    label: VisualLabel | None = None,
    category: FoodCategory | None = None,
    page: Annotated[int, Query(ge=1, le=100_000)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = 10,
) -> Page[FreshnessSummary]:
    return freshness_service.list_assessments(
        db, user, page=page, page_size=page_size, label=label, category=category
    )


@router.get("/assessments/{assessment_id}", response_model=FreshnessDetail)
def get_assessment(assessment_id: uuid.UUID, user: CurrentUser, db: DbSession) -> FreshnessDetail:
    return freshness_service.get_assessment(db, user, assessment_id)


@router.delete(
    "/assessments/{assessment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_csrf_header)],
)
def delete_assessment(assessment_id: uuid.UUID, user: CurrentUser, db: DbSession) -> Response:
    freshness_service.delete_assessment(db, user, assessment_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
