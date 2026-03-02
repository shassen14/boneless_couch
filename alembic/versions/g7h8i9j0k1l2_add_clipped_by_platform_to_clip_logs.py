"""add clipped_by and platform to clip_logs

Revision ID: g7h8i9j0k1l2
Revises: f6a7b8c9d0e1
Create Date: 2026-03-02

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'g7h8i9j0k1l2'
down_revision: Union[str, Sequence[str], None] = 'f6a7b8c9d0e1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('clip_logs', sa.Column('clipped_by', sa.String(), nullable=True))
    op.add_column('clip_logs', sa.Column('platform', sa.String(), nullable=True))
    op.execute("UPDATE clip_logs SET platform = 'twitch'")
    op.alter_column('clip_logs', 'platform', nullable=False)


def downgrade() -> None:
    op.drop_column('clip_logs', 'platform')
    op.drop_column('clip_logs', 'clipped_by')
