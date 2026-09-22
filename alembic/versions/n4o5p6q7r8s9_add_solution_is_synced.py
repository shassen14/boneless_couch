"""add solution_posts.is_synced so resubmissions re-sync their Discord reply

Revision ID: n4o5p6q7r8s9
Revises: m3n4o5p6q7r8
Create Date: 2026-09-22

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'n4o5p6q7r8s9'
down_revision: Union[str, Sequence[str], None] = 'm3n4o5p6q7r8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "solution_posts",
        sa.Column("is_synced", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    # Anything already posted matches its Discord reply.
    op.execute("UPDATE solution_posts SET is_synced = discord_message_id IS NOT NULL")


def downgrade() -> None:
    op.drop_column("solution_posts", "is_synced")
