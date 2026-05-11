"""add Codeforces tables and cf_problems_forum_id to guild_configs

Revision ID: k1l2m3n4o5p6
Revises: j0k1l2m3n4o5
Create Date: 2026-05-11

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'k1l2m3n4o5p6'
down_revision: Union[str, Sequence[str], None] = 'j0k1l2m3n4o5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'cf_problem_attempts',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('stream_event_id', sa.Integer(), nullable=False),
        sa.Column('contest_id', sa.Integer(), nullable=False),
        sa.Column('index', sa.String(10), nullable=False),
        sa.Column('title', sa.String(), nullable=False),
        sa.Column('url', sa.String(), nullable=False),
        sa.Column('rating', sa.Integer(), nullable=True),
        sa.Column('tags', sa.String(), nullable=True),
        sa.Column('vod_timestamp', sa.String(), nullable=True),
        sa.ForeignKeyConstraint(['stream_event_id'], ['stream_events.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('stream_event_id'),
    )

    op.create_table(
        'cf_problem_posts',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('problem_id', sa.String(), nullable=False),
        sa.Column('forum_thread_id', sa.BigInteger(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('problem_id'),
    )

    op.add_column(
        'guild_configs',
        sa.Column('cf_problems_forum_id', sa.BigInteger(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('guild_configs', 'cf_problems_forum_id')
    op.drop_table('cf_problem_posts')
    op.drop_table('cf_problem_attempts')
