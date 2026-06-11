"""add live status message id + stream_event notify trigger

Revision ID: l2m3n4o5p6q7
Revises: k1l2m3n4o5p6
Create Date: 2026-06-11

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'l2m3n4o5p6q7'
down_revision: Union[str, Sequence[str], None] = 'k1l2m3n4o5p6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'stream_sessions',
        sa.Column('discord_live_status_message_id', sa.BigInteger(), nullable=True),
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION notify_stream_update() RETURNS trigger AS $$
        BEGIN
            PERFORM pg_notify('stream_update', NEW.session_id::text);
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER stream_event_notify
        AFTER INSERT ON stream_events
        FOR EACH ROW EXECUTE FUNCTION notify_stream_update();
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS stream_event_notify ON stream_events;")
    op.execute("DROP FUNCTION IF EXISTS notify_stream_update();")
    op.drop_column('stream_sessions', 'discord_live_status_message_id')
