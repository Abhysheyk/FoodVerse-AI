import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class HygieneInspection(Base):
    """Queryable summary of one inspection. Shares its id with an AnalysisRecord whose
    `result` JSON holds the full audit (checklist, findings, disclosures, provider info,
    timestamps). Deleting either row deletes both. There is deliberately no compliance,
    safety, or score column."""

    __tablename__ = "hygiene_inspections"
    __table_args__ = (Index("ix_hygiene_owner_created", "owner_id", "created_at"),)

    analysis_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("analysis_records.id", ondelete="CASCADE"), primary_key=True
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE")
    )
    location_name: Mapped[str] = mapped_column(String(120))
    location_type: Mapped[str] = mapped_column(String(32))
    area: Mapped[str | None] = mapped_column(String(120), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="draft", server_default="draft")
    review_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    finding_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    highest_severity: Mapped[str | None] = mapped_column(String(8), nullable=True)
    photo_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    revision: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )