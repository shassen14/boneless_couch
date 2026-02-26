"""add problems forum

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-02-25

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'guild_configs',
        sa.Column('problems_forum_id', sa.BigInteger(), nullable=True),
    )
    op.create_table(
        'problem_posts',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('platform_id', sa.String(), nullable=False),
        sa.Column('forum_thread_id', sa.BigInteger(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('platform_id'),
    )


def downgrade() -> None:
    op.drop_table('problem_posts')
    op.drop_column('guild_configs', 'problems_forum_id')
