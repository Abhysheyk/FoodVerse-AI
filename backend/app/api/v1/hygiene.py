import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status
from fastapi.responses import HTMLResponse

from app.api.deps import (
    AppSettings,
    CurrentUser,
    DbSession,
    Storage,
    VisionFactory,
    require_csrf_header,
)
from app.domain.hygiene import InspectionStatus, LocationType
from app.schemas.common import MAX_PAGE_SIZE, Page
from app.schemas.hygiene import (
    HygieneCapabilities,
    InspectionCreate,
    InspectionDetail,
    InspectionSummary,
    InspectionUpdate,
    StatusChange,
)
from app.services import hygiene_service

router = APIRouter(prefix="/hygiene", tags=["hygiene"])


@router.get("/capabilities", response_model=HygieneCapabilities)
def capabilities(_user: CurrentUser, settings: AppSettings) -> HygieneCapabilities:
    return hygiene_service.capabilities(settings)


@router.post(
    "/inspections",
    response_model=InspectionDetail,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_csrf_header)],
)
def create_inspection(
    body: InspectionCreate, user: CurrentUser, db: DbSession
) -> InspectionDetail:
    return hygiene_service.create_inspection(db, user, body)


@router.get("/inspections", response_model=Page[InspectionSummary])
def list_inspections(
    user: CurrentUser,
    db: DbSession,
    status_filter: Annotated[InspectionStatus | None, Query(alias="status")] = None,
    location_type: LocationType | None = None,
    page: Annotated[int, Query(ge=1, le=100_000)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = 10,
) -> Page[InspectionSummary]:
    return hygiene_service.list_inspections(
        db,
        user,
        page=page,
        page_size=page_size,
        status=status_filter,
        location_type=location_type,
    )


@router.get("/inspections/{inspection_id}", response_model=InspectionDetail)
def get_inspection(
    inspection_id: uuid.UUID, user: CurrentUser, db: DbSession
) -> InspectionDetail:
    return hygiene_service.get_inspection(db, user, inspection_id)


@router.put(
    "/inspections/{inspection_id}",
    response_model=InspectionDetail,
    dependencies=[Depends(require_csrf_header)],
)
def update_inspection(
    inspection_id: uuid.UUID,
    body: InspectionUpdate,
    user: CurrentUser,
    db: DbSession,
) -> InspectionDetail:
    return hygiene_service.update_inspection(db, user, inspection_id, body)


@router.post(
    "/inspections/{inspection_id}/analyze",
    response_model=InspectionDetail,
    dependencies=[Depends(require_csrf_header)],
)
def analyze_inspection(
    inspection_id: uuid.UUID,
    user: CurrentUser,
    db: DbSession,
    storage: Storage,
    settings: AppSettings,
    make_provider: VisionFactory,
) -> InspectionDetail:
    return hygiene_service.analyze_inspection(
        db, storage, settings, user, inspection_id, make_provider
    )


@router.post(
    "/inspections/{inspection_id}/submit",
    response_model=InspectionDetail,
    dependencies=[Depends(require_csrf_header)],
)
def submit_inspection(
    inspection_id: uuid.UUID, user: CurrentUser, db: DbSession
) -> InspectionDetail:
    return hygiene_service.submit_inspection(db, user, inspection_id)


@router.post(
    "/inspections/{inspection_id}/approve",
    response_model=InspectionDetail,
    dependencies=[Depends(require_csrf_header)],
)
def approve_inspection(
    inspection_id: uuid.UUID,
    body: StatusChange,
    user: CurrentUser,
    db: DbSession,
) -> InspectionDetail:
    return hygiene_service.approve_inspection(db, user, inspection_id, body)


@router.post(
    "/inspections/{inspection_id}/reject",
    response_model=InspectionDetail,
    dependencies=[Depends(require_csrf_header)],
)
def reject_inspection(
    inspection_id: uuid.UUID,
    body: StatusChange,
    user: CurrentUser,
    db: DbSession,
) -> InspectionDetail:
    return hygiene_service.reject_inspection(db, user, inspection_id, body)


@router.delete(
    "/inspections/{inspection_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_csrf_header)],
)
def delete_inspection(
    inspection_id: uuid.UUID, user: CurrentUser, db: DbSession
) -> Response:
    hygiene_service.delete_inspection(db, user, inspection_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/inspections/{inspection_id}/report", response_class=HTMLResponse)
def report(
    inspection_id: uuid.UUID, user: CurrentUser, db: DbSession
) -> HTMLResponse:
    return HTMLResponse(
        hygiene_service.render_report_html(db, user, inspection_id)
    )