"""add partial unique index for one active session per platform

Revision ID: m3n4o5p6q7r8
Revises: l2m3n4o5p6q7
Create Date: 2026-06-15

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'm3n4o5p6q7r8'
down_revision: Union[str, Sequence[str], None] = 'l2m3n4o5p6q7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

INDEX_NAME = "uq_active_session_per_platform"


def upgrade() -> None:
    # Collapse any pre-existing duplicate active sessions (keep newest per
    # platform) so the unique index below can be created cleanly.
    op.execute(
        """
        UPDATE stream_sessions
        SET is_active = false
        WHERE is_active = true
          AND id NOT IN (
            SELECT DISTINCT ON (platform) id
            FROM stream_sessions
            WHERE is_active = true
            ORDER BY platform, start_time DESC
          );
        """
    )
    op.create_index(
        INDEX_NAME,
        "stream_sessions",
        ["platform"],
        unique=True,
        postgresql_where=sa.text("is_active"),
    )


def downgrade() -> None:
    op.drop_index(INDEX_NAME, table_name="stream_sessions")
