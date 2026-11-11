import enum
import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class MealPlanSource(enum.StrEnum):
    AI = "ai"
    MANUAL = "manual"
    COPIED = "copied"


class MealPlanStatus(enum.StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    ARCHIVED = "archived"


def _enum(e: type[enum.StrEnum], name: str, length: int = 16) -> Enum:
    return Enum(
        e,
        name=name,
        native_enum=False,
        create_constraint=True,
        values_callable=lambda x: [m.value for m in x],
        length=length,
    )


class MealPlan(Base):
    """One week's plan for one user. Structure lives in plan_json so edits are atomic;
    the audit fields (source, model_meta) are separate columns for querying."""

    __tablename__ = "meal_plans"
    __table_args__ = (
        Index("ix_meal_plans_owner_week", "owner_id", "week_start_date"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE")
    )
    title: Mapped[str] = mapped_column(String(200))
    week_start_date: Mapped[date] = mapped_column(Date)
    source: Mapped[MealPlanSource] = mapped_column(_enum(MealPlanSource, "meal_plan_source"))
    status: Mapped[MealPlanStatus] = mapped_column(
        _enum(MealPlanStatus, "meal_plan_status"), default=MealPlanStatus.DRAFT
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    plan_json: Mapped[dict[str, Any]] = mapped_column(JSONB)
    estimate_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    estimated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    model_meta: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    revision: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    grocery_lists: Mapped[list["GroceryList"]] = relationship(
        back_populates="plan", cascade="save-update", passive_deletes=True
    )


class GroceryList(Base):
    __tablename__ = "grocery_lists"
    __table_args__ = (Index("ix_grocery_lists_owner_created", "owner_id", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE")
    )
    plan_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("meal_plans.id", ondelete="SET NULL"), nullable=True
    )
    title: Mapped[str] = mapped_column(String(200))
    revision: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    plan: Mapped[MealPlan | None] = relationship(back_populates="grocery_lists")
    items: Mapped[list["GroceryItem"]] = relationship(
        back_populates="grocery_list", cascade="all, delete-orphan"
    )


class GroceryItem(Base):
    __tablename__ = "grocery_items"
    __table_args__ = (Index("ix_grocery_items_list_position", "list_id", "position"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    list_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("grocery_lists.id", ondelete="CASCADE")
    )
    name: Mapped[str] = mapped_column(String(200))
    quantity: Mapped[float] = mapped_column(Numeric(10, 2))
    unit: Mapped[str] = mapped_column(String(16))
    checked: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    position: Mapped[int] = mapped_column(Integer)
    notes: Mapped[str | None] = mapped_column(String(200), nullable=True)

    grocery_list: Mapped[GroceryList] = relationship(back_populates="items")