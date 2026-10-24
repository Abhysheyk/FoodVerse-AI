import uuid
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Query, UploadFile, status
from fastapi.responses import StreamingResponse

from app.api.deps import AppSettings, CurrentUser, DbSession, Storage, require_csrf_header
from app.repositories import media as media_repo
from app.schemas.common import Page
from app.schemas.media import MediaRead
from app.services import media_service

router = APIRouter(prefix="/media", tags=["media"])


@router.post(
    "",
    response_model=MediaRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_csrf_header)],
)
def upload_media(
    file: Annotated[UploadFile, File(description="JPEG, PNG or WebP image")],
    user: CurrentUser,
    db: DbSession,
    storage: Storage,
    settings: AppSettings,
) -> MediaRead:
    return MediaRead.model_validate(media_service.upload(db, storage, settings, user, file))


@router.get("", response_model=Page[MediaRead])
def list_media(
    user: CurrentUser,
    db: DbSession,
    page: Annotated[int, Query(ge=1, le=100_000)] = 1,
    page_size: Annotated[int, Query(ge=1, le=50)] = 12,
) -> Page[MediaRead]:
    rows, total = media_repo.list_page(db, user.id, limit=page_size, offset=(page - 1) * page_size)
    return Page.build([MediaRead.model_validate(r) for r in rows], total, page, page_size)


@router.get("/{media_id}", response_model=MediaRead)
def get_media(media_id: uuid.UUID, user: CurrentUser, db: DbSession) -> MediaRead:
    return MediaRead.model_validate(media_service.get_owned_or_404(db, user, media_id))


@router.get("/{media_id}/content")
def get_media_content(
    media_id: uuid.UUID,
    user: CurrentUser,
    db: DbSession,
    storage: Storage,
    download: bool = False,
) -> StreamingResponse:
    asset, stream = media_service.open_content(db, storage, user, media_id)
    disposition = "inline"
    if download:
        disposition = f"attachment; filename*=UTF-8''{quote(asset.display_name, safe='')}"
    return StreamingResponse(
        stream,
        media_type=asset.content_type,  # from our own detection, never the client's claim
        headers={
            "Content-Length": str(asset.size_bytes),
            "Content-Disposition": disposition,
            # Defence in depth: even if rendered as a document, nothing may execute or load.
            "Content-Security-Policy": "default-src 'none'; sandbox",
            "Cache-Control": "private, no-store",
        },
    )


@router.delete(
    "/{media_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_csrf_header)],
)
def delete_media(media_id: uuid.UUID, user: CurrentUser, db: DbSession, storage: Storage) -> None:
    media_service.delete(db, storage, user, media_id)
