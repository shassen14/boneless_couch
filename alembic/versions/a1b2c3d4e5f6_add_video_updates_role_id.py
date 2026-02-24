"""add video_updates_role_id to guild_configs

Revision ID: a1b2c3d4e5f6
Revises: dca72fdb4d78
Create Date: 2026-02-24

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = 'dca72fdb4d78'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'guild_configs',
        sa.Column('video_updates_role_id', sa.BigInteger(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('guild_configs', 'video_updates_role_id')
