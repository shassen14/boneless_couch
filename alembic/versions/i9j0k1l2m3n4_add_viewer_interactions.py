"""add viewer_interactions table

Revision ID: i9j0k1l2m3n4
Revises: h8i9j0k1l2m3
Create Date: 2026-04-22

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'i9j0k1l2m3n4'
down_revision: Union[str, Sequence[str], None] = 'h8i9j0k1l2m3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'viewer_interactions',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('session_id', sa.Integer(), nullable=True),
        sa.Column('timestamp', sa.DateTime(timezone=True), nullable=False),
        sa.Column('interaction_type', sa.String(), nullable=False),
        sa.Column('username', sa.String(), nullable=True),
        sa.Column('display_name', sa.String(), nullable=True),
        sa.Column('tier', sa.String(), nullable=True),
        sa.Column('cumulative_months', sa.Integer(), nullable=True),
        sa.Column('streak_months', sa.Integer(), nullable=True),
        sa.Column('gift_count', sa.Integer(), nullable=True),
        sa.Column('bits', sa.Integer(), nullable=True),
        sa.Column('viewer_count', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['session_id'], ['stream_sessions.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_viewer_interactions_type_ts', 'viewer_interactions', ['interaction_type', 'timestamp'])
    op.create_index('ix_viewer_interactions_username', 'viewer_interactions', ['username'])


def downgrade() -> None:
    op.drop_index('ix_viewer_interactions_username', table_name='viewer_interactions')
    op.drop_index('ix_viewer_interactions_type_ts', table_name='viewer_interactions')
    op.drop_table('viewer_interactions')
