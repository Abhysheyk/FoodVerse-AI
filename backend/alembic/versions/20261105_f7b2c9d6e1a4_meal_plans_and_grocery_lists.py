"""meal plans, grocery lists and Phase 7 preferences

Revision ID: f7b2c9d6e1a4
Revises: 0ee6b989a2dc
Create Date: 2026-11-05 09:00:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = 'f7b2c9d6e1a4'
down_revision: str | None = '0ee6b989a2dc'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('user_preferences', sa.Column('dietary_pattern', sa.String(32), nullable=True))
    op.add_column(
        'user_preferences',
        sa.Column(
            'excluded_ingredients',
            postgresql.ARRAY(sa.String(50)),
            server_default='{}',
            nullable=False,
        ),
    )
    op.add_column(
        'user_preferences',
        sa.Column(
            'preferred_cuisines',
            postgresql.ARRAY(sa.String(32)),
            server_default='{}',
            nullable=False,
        ),
    )
    op.add_column(
        'user_preferences',
        sa.Column('budget', sa.String(16), server_default='any', nullable=False),
    )
    op.add_column(
        'user_preferences',
        sa.Column('max_cooking_minutes', sa.Integer(), nullable=True),
    )
    op.add_column(
        'user_preferences',
        sa.Column('default_servings', sa.Integer(), server_default='1', nullable=False),
    )
    op.add_column(
        'user_preferences',
        sa.Column(
            'pantry_ingredients',
            postgresql.ARRAY(sa.String(80)),
            server_default='{}',
            nullable=False,
        ),
    )
    op.add_column(
        'user_preferences',
        sa.Column('nutrition_targets', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )

    op.create_table(
        'meal_plans',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('owner_id', sa.UUID(), nullable=False),
        sa.Column('title', sa.String(200), nullable=False),
        sa.Column('week_start_date', sa.Date(), nullable=False),
        sa.Column(
            'source',
            sa.Enum(
                'ai', 'manual', 'copied', name='meal_plan_source',
                native_enum=False, create_constraint=True, length=16,
            ),
            nullable=False,
        ),
        sa.Column(
            'status',
            sa.Enum(
                'draft', 'active', 'archived', name='meal_plan_status',
                native_enum=False, create_constraint=True, length=16,
            ),
            nullable=False,
        ),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('plan_json', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('estimate_json', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('estimated_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('model_meta', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('revision', sa.Integer(), server_default='1', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(
            ['owner_id'], ['users.id'], name=op.f('fk_meal_plans_owner_id_users'), ondelete='CASCADE'
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_meal_plans')),
    )
    op.create_index('ix_meal_plans_owner_week', 'meal_plans', ['owner_id', 'week_start_date'])

    op.create_table(
        'grocery_lists',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('owner_id', sa.UUID(), nullable=False),
        sa.Column('plan_id', sa.UUID(), nullable=True),
        sa.Column('title', sa.String(200), nullable=False),
        sa.Column('revision', sa.Integer(), server_default='1', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(
            ['owner_id'], ['users.id'], name=op.f('fk_grocery_lists_owner_id_users'), ondelete='CASCADE'
        ),
        sa.ForeignKeyConstraint(
            ['plan_id'], ['meal_plans.id'], name=op.f('fk_grocery_lists_plan_id_meal_plans'), ondelete='SET NULL'
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_grocery_lists')),
    )
    op.create_index('ix_grocery_lists_owner_created', 'grocery_lists', ['owner_id', 'created_at'])

    op.create_table(
        'grocery_items',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('list_id', sa.UUID(), nullable=False),
        sa.Column('name', sa.String(200), nullable=False),
        sa.Column('quantity', sa.Numeric(10, 2), nullable=False),
        sa.Column('unit', sa.String(16), nullable=False),
        sa.Column('checked', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('position', sa.Integer(), nullable=False),
        sa.Column('notes', sa.String(200), nullable=True),
        sa.ForeignKeyConstraint(
            ['list_id'], ['grocery_lists.id'],
            name=op.f('fk_grocery_items_list_id_grocery_lists'), ondelete='CASCADE'
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_grocery_items')),
    )
    op.create_index('ix_grocery_items_list_position', 'grocery_items', ['list_id', 'position'])


def downgrade() -> None:
    op.drop_index('ix_grocery_items_list_position', table_name='grocery_items')
    op.drop_table('grocery_items')
    op.drop_index('ix_grocery_lists_owner_created', table_name='grocery_lists')
    op.drop_table('grocery_lists')
    op.drop_index('ix_meal_plans_owner_week', table_name='meal_plans')
    op.drop_table('meal_plans')
    op.drop_column('user_preferences', 'nutrition_targets')
    op.drop_column('user_preferences', 'pantry_ingredients')
    op.drop_column('user_preferences', 'default_servings')
    op.drop_column('user_preferences', 'max_cooking_minutes')
    op.drop_column('user_preferences', 'budget')
    op.drop_column('user_preferences', 'preferred_cuisines')
    op.drop_column('user_preferences', 'excluded_ingredients')
    op.drop_column('user_preferences', 'dietary_pattern')