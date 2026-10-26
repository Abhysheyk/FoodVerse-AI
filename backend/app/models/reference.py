import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ReferenceFood(Base):
    """A food from an offline reference table (e.g. IFCT), imported from a file the operator
    supplies. Every row carries its dataset, version, citation and licence note. The table is
    empty until an operator imports data; nothing is bundled or invented."""

    __tablename__ = "reference_foods"
    __table_args__ = (
        UniqueConstraint("dataset", "source_id", name="uq_reference_foods_dataset_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    dataset: Mapped[str] = mapped_column(String(80))
    dataset_version: Mapped[str] = mapped_column(String(40))
    source_id: Mapped[str] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(200))
    name_normalized: Mapped[str] = mapped_column(String(200), index=True)
    category: Mapped[str | None] = mapped_column(String(80), nullable=True)
    # Per 100 g, only the nutrients the dataset reports (keys from app.nutrition.nutrients).
    nutrients: Mapped[dict[str, Any]] = mapped_column(JSONB)
    citation: Mapped[str] = mapped_column(Text)
    license_note: Mapped[str] = mapped_column(Text)
    imported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
