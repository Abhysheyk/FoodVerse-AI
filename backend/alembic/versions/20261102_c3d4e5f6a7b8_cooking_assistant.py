"""cooking assistant: conversations, messages, recipes

Revision ID: c3d4e5f6a7b8
Revises: 0ee6b989a2dc
Create Date: 2026-11-02 09:00:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c3d4e5f6a7b8"
down_revision: str | None = "0ee6b989a2dc"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "cooking_conversations",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("owner_id", sa.UUID(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], name=op.f("fk_cooking_conversations_owner_id_users"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_cooking_conversations")),
    )
    op.create_index(
        "ix_cooking_conversations_owner_updated", "cooking_conversations", ["owner_id", "updated_at"]
    )
    op.create_table(
        "recipes",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("analysis_id", sa.UUID(), nullable=True),
        sa.Column("owner_id", sa.UUID(), nullable=False),
        sa.Column("conversation_id", sa.UUID(), nullable=True),
        sa.Column("status", sa.Enum("suggested", "saved", name="recipe_status", native_enum=False, create_constraint=True, length=16), nullable=False),
        sa.Column("favorite", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("title", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("servings", sa.Integer(), nullable=False),
        sa.Column("prep_minutes", sa.Integer(), nullable=True),
        sa.Column("cook_minutes", sa.Integer(), nullable=True),
        sa.Column("equipment", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("ingredients", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("steps", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("substitutions", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("dietary_tags", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("allergen_warnings", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("safety_notes", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("tips", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("beginner_notes", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("provider", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("nutrition", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revision", sa.Integer(), server_default="1", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["analysis_id"], ["analysis_records.id"], name=op.f("fk_recipes_analysis_id_analysis_records"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], name=op.f("fk_recipes_owner_id_users"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["conversation_id"], ["cooking_conversations.id"], name=op.f("fk_recipes_conversation_id_cooking_conversations"), ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_recipes")),
        sa.UniqueConstraint("analysis_id", name=op.f("uq_recipes_analysis_id")),
    )
    op.create_index("ix_recipes_owner_created", "recipes", ["owner_id", "created_at"])
    op.create_index("ix_recipes_owner_title", "recipes", ["owner_id", "title"])
    op.create_table(
        "cooking_messages",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("conversation_id", sa.UUID(), nullable=False),
        sa.Column("owner_id", sa.UUID(), nullable=False),
        sa.Column("role", sa.Enum("user", "assistant", name="cooking_message_role", native_enum=False, create_constraint=True, length=16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("recipe_id", sa.UUID(), nullable=True),
        sa.Column("warnings", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["conversation_id"], ["cooking_conversations.id"], name=op.f("fk_cooking_messages_conversation_id_cooking_conversations"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], name=op.f("fk_cooking_messages_owner_id_users"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["recipe_id"], ["recipes.id"], name=op.f("fk_cooking_messages_recipe_id_recipes"), ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_cooking_messages")),
    )
    op.create_index("ix_cooking_messages_conversation", "cooking_messages", ["conversation_id", "position"])


def downgrade() -> None:
    op.drop_index("ix_cooking_messages_conversation", table_name="cooking_messages")
    op.drop_table("cooking_messages")
    op.drop_index("ix_recipes_owner_title", table_name="recipes")
    op.drop_index("ix_recipes_owner_created", table_name="recipes")
    op.drop_table("recipes")
    op.drop_index("ix_cooking_conversations_owner_updated", table_name="cooking_conversations")
    op.drop_table("cooking_conversations")