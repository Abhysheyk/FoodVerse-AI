import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import CurrentUser, DbSession, require_csrf_header
from app.models import ModuleKey
from app.schemas.common import MAX_PAGE_SIZE, Page
from app.schemas.history import HistoryDetail, HistoryItem
from app.services import history_service

router = APIRouter(prefix="/history", tags=["history"])


@router.get("", response_model=Page[HistoryItem])
def list_history(
    user: CurrentUser,
    db: DbSession,
    module: ModuleKey | None = None,
    page: Annotated[int, Query(ge=1, le=100_000)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = 20,
) -> Page[HistoryItem]:
    return history_service.list_history(db, user, module=module, page=page, page_size=page_size)


@router.get("/{record_id}", response_model=HistoryDetail)
def get_history(record_id: uuid.UUID, user: CurrentUser, db: DbSession) -> HistoryDetail:
    return HistoryDetail.model_validate(history_service.get_owned_or_404(db, user, record_id))


@router.delete(
    "/{record_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_csrf_header)],
)
def delete_history(record_id: uuid.UUID, user: CurrentUser, db: DbSession) -> None:
    history_service.delete(db, user, record_id)
