import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Enum, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class MealCategory(enum.StrEnum):
    BREAKFAST = "breakfast"
    LUNCH = "lunch"
    DINNER = "dinner"
    SNACK = "snack"


class MealLog(Base):
    """Queryable facts about a saved meal. It shares its id with an AnalysisRecord, which holds
    the complete audit result (model observations, confirmed items, source snapshots, per-item
    and total calculations). Deleting either one deletes both."""

    __tablename__ = "meal_logs"
    __table_args__ = (Index("ix_meal_logs_owner_eaten", "owner_id", "eaten_at"),)

    analysis_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("analysis_records.id", ondelete="CASCADE"), primary_key=True
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE")
    )
    eaten_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    category: Mapped[MealCategory] = mapped_column(
        Enum(
            MealCategory,
            name="meal_category",
            native_enum=False,
            create_constraint=True,
            values_callable=lambda e: [m.value for m in e],
            length=16,
        )
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Deterministic totals at save time (same shape as the audit result's "totals").
    totals: Mapped[dict[str, Any]] = mapped_column(JSONB)
    item_count: Mapped[int] = mapped_column(Integer)
    revision: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    # Short label shown in lists, e.g. "rice, dal, salad".
    items_label: Mapped[str] = mapped_column(String(200), default="")
