import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class RecipeStatus(enum.StrEnum):
    SUGGESTED = "suggested"  # produced by the model, not yet kept by the user
    SAVED = "saved"


class MessageRole(enum.StrEnum):
    USER = "user"
    ASSISTANT = "assistant"


class CookingConversation(Base):
    __tablename__ = "cooking_conversations"
    __table_args__ = (
        Index("ix_cooking_conversations_owner_updated", "owner_id", "updated_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE")
    )
    title: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Recipe(Base):
    """A model-suggested recipe. `id` equals the AnalysisRecord id once saved, so a recipe
    and its history entry share one identity and deleting either removes both."""

    __tablename__ = "recipes"
    __table_args__ = (
        Index("ix_recipes_owner_created", "owner_id", "created_at"),
        Index("ix_recipes_owner_title", "owner_id", "title"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    analysis_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("analysis_records.id", ondelete="CASCADE"),
        unique=True,
        nullable=True,
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE")
    )
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("cooking_conversations.id", ondelete="SET NULL"),
        nullable=True,
    )
    status: Mapped[RecipeStatus] = mapped_column(
        Enum(
            RecipeStatus,
            name="recipe_status",
            native_enum=False,
            create_constraint=True,
            values_callable=lambda e: [m.value for m in e],
            length=16,
        ),
        default=RecipeStatus.SUGGESTED,
    )
    favorite: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")

    title: Mapped[str] = mapped_column(String(120))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    servings: Mapped[int] = mapped_column(Integer)
    prep_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cook_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)

    equipment: Mapped[list[Any]] = mapped_column(JSONB, default=list)
    ingredients: Mapped[list[Any]] = mapped_column(JSONB, default=list)
    steps: Mapped[list[Any]] = mapped_column(JSONB, default=list)
    substitutions: Mapped[list[Any]] = mapped_column(JSONB, default=list)
    dietary_tags: Mapped[list[Any]] = mapped_column(JSONB, default=list)
    allergen_warnings: Mapped[list[Any]] = mapped_column(JSONB, default=list)
    safety_notes: Mapped[list[Any]] = mapped_column(JSONB, default=list)
    tips: Mapped[list[Any]] = mapped_column(JSONB, default=list)
    beginner_notes: Mapped[list[Any]] = mapped_column(JSONB, default=list)

    provider: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    nutrition: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    generated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    revision: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class CookingMessage(Base):
    __tablename__ = "cooking_messages"
    __table_args__ = (
        Index("ix_cooking_messages_conversation", "conversation_id", "position"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("cooking_conversations.id", ondelete="CASCADE"),
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE")
    )
    role: Mapped[MessageRole] = mapped_column(
        Enum(
            MessageRole,
            name="cooking_message_role",
            native_enum=False,
            create_constraint=True,
            values_callable=lambda e: [m.value for m in e],
            length=16,
        )
    )
    content: Mapped[str] = mapped_column(Text)
    recipe_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("recipes.id", ondelete="SET NULL"),
        nullable=True,
    )
    warnings: Mapped[list[Any]] = mapped_column(JSONB, default=list)
    position: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )