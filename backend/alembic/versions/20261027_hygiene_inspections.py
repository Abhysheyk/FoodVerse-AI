"""hygiene inspections

Revision ID: f3c9d2a1b7e6
Revises: 0ee6b989a2dc
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f3c9d2a1b7e6"
down_revision: str | None = "0ee6b989a2dc"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "hygiene_inspections",
        sa.Column("analysis_id", sa.UUID(), nullable=False),
        sa.Column("owner_id", sa.UUID(), nullable=False),
        sa.Column("location_name", sa.String(length=120), nullable=False),
        sa.Column("location_type", sa.String(length=32), nullable=False),
        sa.Column("area", sa.String(length=120), nullable=True),
        sa.Column("status", sa.String(length=16), server_default="draft", nullable=False),
        sa.Column("review_notes", sa.Text(), nullable=True),
        sa.Column("finding_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("highest_severity", sa.String(length=8), nullable=True),
        sa.Column("photo_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("revision", sa.Integer(), server_default="1", nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["analysis_id"],
            ["analysis_records.id"],
            name=op.f("fk_hygiene_inspections_analysis_id_analysis_records"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["owner_id"],
            ["users.id"],
            name=op.f("fk_hygiene_inspections_owner_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("analysis_id", name=op.f("pk_hygiene_inspections")),
    )
    op.create_index(
        "ix_hygiene_owner_created",
        "hygiene_inspections",
        ["owner_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_hygiene_owner_created", table_name="hygiene_inspections")
    op.drop_table("hygiene_inspections")