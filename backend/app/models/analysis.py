import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Enum, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ModuleKey(enum.StrEnum):
    FOOD_RECOGNITION = "food_recognition"
    FRESHNESS = "freshness"
    HYGIENE = "hygiene"
    COOKING = "cooking"
    MEAL_PLANNING = "meal_planning"


class AnalysisStatus(enum.StrEnum):
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"


def _enum(e: type[enum.StrEnum], name: str) -> Enum:
    return Enum(
        e,
        name=name,
        native_enum=False,
        create_constraint=True,
        values_callable=lambda x: [m.value for m in x],
        length=32,
    )


class AnalysisRecord(Base):
    """One entry in a user's activity history, shared by every feature module.

    Phase 2 creates the table and read/delete access only. Feature modules (later phases)
    are the only writers; nothing in this phase inserts records.
    """

    __tablename__ = "analysis_records"
    __table_args__ = (Index("ix_analysis_records_owner_created", "owner_id", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE")
    )
    module: Mapped[ModuleKey] = mapped_column(_enum(ModuleKey, "module_key"))
    status: Mapped[AnalysisStatus] = mapped_column(_enum(AnalysisStatus, "analysis_status"))
    title: Mapped[str] = mapped_column(String(200))
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Structured, module-specific output. Shape is defined by each module's own schema.
    result: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    media_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("media_assets.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
