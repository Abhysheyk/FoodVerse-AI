import enum
import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Enum, Float, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class MediaKind(enum.StrEnum):
    IMAGE = "image"
    VIDEO = "video"  # reserved: validation is not implemented until Phase 7
    AUDIO = "audio"  # reserved: validation is not implemented until Phase 7


class MediaAsset(Base):
    """Metadata for one stored file. The bytes live in the storage backend under storage_key.

    storage_key and any filesystem path are server-generated and never exposed by the API.
    """

    __tablename__ = "media_assets"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[MediaKind] = mapped_column(
        Enum(
            MediaKind,
            name="media_kind",
            native_enum=False,
            create_constraint=True,
            values_callable=lambda e: [m.value for m in e],
            length=16,
        )
    )
    # Determined by the server from the file contents, never from the client.
    content_type: Mapped[str] = mapped_column(String(64))
    # Sanitised, display-only. Never used to build a path.
    display_name: Mapped[str] = mapped_column(String(120))
    storage_key: Mapped[str] = mapped_column(String(64), unique=True)
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    sha256: Mapped[str] = mapped_column(String(64))
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
