"""Upload, read and delete media. Every function that touches an existing asset goes through
`get_owned_or_404`, so there is no code path that reads or deletes another user's file."""

import logging
import uuid
from collections.abc import Iterator
from hashlib import sha256
from typing import BinaryIO

from fastapi import UploadFile
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import AppError, NotFoundError, PayloadTooLargeError
from app.media.storage import StorageBackend, StorageError, iter_chunks
from app.media.validation import sanitize_display_name, validate_and_process
from app.models import MediaAsset, User
from app.repositories import media as media_repo

logger = logging.getLogger("app.media")
_READ_CHUNK = 64 * 1024


def read_upload(file: UploadFile, max_bytes: int) -> bytes:
    """Read at most max_bytes (+1 to detect overflow) so a huge file never fills memory."""
    chunks: list[bytes] = []
    total = 0
    while chunk := file.file.read(_READ_CHUNK):
        total += len(chunk)
        if total > max_bytes:
            raise PayloadTooLargeError(
                f"File is too large. The maximum size is {max_bytes // (1024 * 1024)} MB."
                if max_bytes >= 1024 * 1024
                else f"File is too large. The maximum size is {max_bytes} bytes."
            )
        chunks.append(chunk)
    return b"".join(chunks)


def get_owned_or_404(db: Session, user: User, media_id: uuid.UUID) -> MediaAsset:
    asset = media_repo.get_owned(db, media_id, user.id)
    if asset is None:  # same response whether it is missing or belongs to someone else
        raise NotFoundError("Media not found.", code="media_not_found")
    return asset


def upload(
    db: Session, storage: StorageBackend, settings: Settings, user: User, file: UploadFile
) -> MediaAsset:
    raw = read_upload(file, settings.max_upload_bytes)
    processed = validate_and_process(
        raw, file.filename, file.content_type, settings.max_image_pixels
    )

    count, used = media_repo.usage(db, user.id)
    if used + len(processed.data) > settings.user_media_quota_bytes:
        raise AppError(
            "Your media storage quota is full. Delete some files and try again.",
            code="quota_exceeded",
            status_code=413,
        )

    asset_id = uuid.uuid4()
    key = f"{asset_id.hex[:2]}/{asset_id.hex}.{processed.extension}"
    asset = MediaAsset(
        id=asset_id,
        owner_id=user.id,
        kind=processed.kind,
        content_type=processed.content_type,
        display_name=sanitize_display_name(file.filename),
        storage_key=key,
        size_bytes=len(processed.data),
        sha256=sha256(processed.data).hexdigest(),
        width=processed.width,
        height=processed.height,
        duration_seconds=processed.duration_seconds,
    )
    storage.put(key, processed.data)
    try:
        media_repo.add(db, asset)
        db.commit()
    except Exception:
        db.rollback()
        storage.delete(key)  # never leave an unreferenced file behind
        raise
    db.refresh(asset)
    logger.info(
        "media_uploaded user_id=%s media_id=%s bytes=%s", user.id, asset.id, asset.size_bytes
    )
    return asset


def open_content(
    db: Session, storage: StorageBackend, user: User, media_id: uuid.UUID
) -> tuple[MediaAsset, Iterator[bytes]]:
    asset = get_owned_or_404(db, user, media_id)
    try:
        handle: BinaryIO = storage.open(asset.storage_key)
    except StorageError:
        logger.error("media_content_missing media_id=%s", asset.id)
        raise NotFoundError("Media content is unavailable.", code="media_not_found") from None
    return asset, iter_chunks(handle)


def delete(db: Session, storage: StorageBackend, user: User, media_id: uuid.UUID) -> None:
    asset = get_owned_or_404(db, user, media_id)
    key = asset.storage_key
    db.delete(asset)
    db.commit()
    try:
        storage.delete(key)
    except (OSError, StorageError):
        logger.error("media_file_delete_failed media_id=%s", media_id)  # row is gone; file orphaned
