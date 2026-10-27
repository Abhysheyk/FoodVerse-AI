import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class FreshnessAssessment(Base):
    """Queryable facts about a saved freshness check. It shares its id with an AnalysisRecord,
    which holds the complete audit result (inputs, model evidence, label, advice, provider).
    Deleting either one deletes both. There is deliberately no score or "safe" column."""

    __tablename__ = "freshness_assessments"
    __table_args__ = (Index("ix_freshness_owner_created", "owner_id", "created_at"),)

    analysis_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("analysis_records.id", ondelete="CASCADE"), primary_key=True
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE")
    )
    food_name: Mapped[str] = mapped_column(String(80))
    food_category: Mapped[str] = mapped_column(String(32))
    label: Mapped[str] = mapped_column(String(32))
    advice_level: Mapped[str] = mapped_column(String(32))
    image_analysed: Mapped[bool] = mapped_column(Boolean)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
