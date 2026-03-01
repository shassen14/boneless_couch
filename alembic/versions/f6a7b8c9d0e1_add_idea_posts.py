"""add idea_posts table and ideas_channel_id to guild_configs

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-03-01

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f6a7b8c9d0e1'
down_revision: Union[str, Sequence[str], None] = 'e5f6a7b8c9d0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'guild_configs',
        sa.Column('ideas_channel_id', sa.BigInteger(), nullable=True),
    )
    op.create_table(
        'idea_posts',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('text', sa.String(), nullable=False),
        sa.Column('submitted_by', sa.String(), nullable=False),
        sa.Column('platform', sa.String(), nullable=False),
        sa.Column('discord_message_id', sa.BigInteger(), nullable=True),
        sa.Column('removed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade() -> None:
    op.drop_table('idea_posts')
    op.drop_column('guild_configs', 'ideas_channel_id')
