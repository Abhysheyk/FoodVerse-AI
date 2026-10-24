import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.user import User


class UnitSystem(enum.StrEnum):
    METRIC = "metric"
    IMPERIAL = "imperial"


class UserPreferences(Base):
    """One row per user. Allergies and dietary preferences are user-declared, not inferred."""

    __tablename__ = "user_preferences"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    unit_system: Mapped[UnitSystem] = mapped_column(
        Enum(
            UnitSystem,
            name="unit_system",
            native_enum=False,
            create_constraint=True,
            values_callable=lambda e: [m.value for m in e],
            length=16,
        ),
        default=UnitSystem.METRIC,
        server_default=UnitSystem.METRIC.value,
    )
    dietary_preferences: Mapped[list[str]] = mapped_column(
        ARRAY(String(32)), default=list, server_default="{}"
    )
    allergies: Mapped[list[str]] = mapped_column(
        ARRAY(String(50)), default=list, server_default="{}"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    user: Mapped["User"] = relationship(back_populates="preferences")
