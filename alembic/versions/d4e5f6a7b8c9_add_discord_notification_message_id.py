"""add discord_notification_message_id to stream_sessions

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-02-27

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd4e5f6a7b8c9'
down_revision: Union[str, Sequence[str], None] = 'c3d4e5f6a7b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'stream_sessions',
        sa.Column('discord_notification_message_id', sa.BigInteger(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('stream_sessions', 'discord_notification_message_id')
