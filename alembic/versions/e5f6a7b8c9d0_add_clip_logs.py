"""add clip_logs table and clip_showcase_channel_id to guild_configs

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-02-28

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e5f6a7b8c9d0'
down_revision: Union[str, Sequence[str], None] = 'd4e5f6a7b8c9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'guild_configs',
        sa.Column('clip_showcase_channel_id', sa.BigInteger(), nullable=True),
    )
    op.create_table(
        'clip_logs',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('stream_event_id', sa.Integer(), nullable=False),
        sa.Column('clip_id', sa.String(), nullable=False),
        sa.Column('title', sa.String(), nullable=False),
        sa.Column('url', sa.String(), nullable=False),
        sa.Column('vod_timestamp', sa.String(), nullable=True),
        sa.Column('discord_message_id', sa.BigInteger(), nullable=True),
        sa.ForeignKeyConstraint(['stream_event_id'], ['stream_events.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('stream_event_id'),
    )


def downgrade() -> None:
    op.drop_table('clip_logs')
    op.drop_column('guild_configs', 'clip_showcase_channel_id')
