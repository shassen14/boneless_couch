"""normalize stream events

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-02-26

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c3d4e5f6a7b8'
down_revision: Union[str, Sequence[str], None] = 'b2c3d4e5f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'problem_attempts',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('stream_event_id', sa.Integer(), nullable=False),
        sa.Column('slug', sa.String(), nullable=False),
        sa.Column('title', sa.String(), nullable=False),
        sa.Column('url', sa.String(), nullable=True),
        sa.Column('difficulty', sa.String(), nullable=True),
        sa.Column('rating', sa.Integer(), nullable=True),
        sa.Column('vod_timestamp', sa.String(), nullable=True),
        sa.ForeignKeyConstraint(['stream_event_id'], ['stream_events.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('stream_event_id'),
    )
    op.create_table(
        'project_logs',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('stream_event_id', sa.Integer(), nullable=False),
        sa.Column('url', sa.String(), nullable=True),
        sa.Column('title', sa.String(), nullable=False),
        sa.Column('description', sa.String(), nullable=True),
        sa.Column('vod_timestamp', sa.String(), nullable=True),
        sa.ForeignKeyConstraint(['stream_event_id'], ['stream_events.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('stream_event_id'),
    )
    op.create_table(
        'solution_posts',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('problem_slug', sa.String(), nullable=False),
        sa.Column('platform', sa.String(), nullable=False),
        sa.Column('username', sa.String(), nullable=False),
        sa.Column('url', sa.String(), nullable=False),
        sa.Column('vod_timestamp', sa.String(), nullable=True),
        sa.Column('discord_message_id', sa.BigInteger(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('problem_slug', 'platform', 'username'),
    )

    # Rename leetcode events to problem_attempt before migrating
    op.execute("UPDATE stream_events SET event_type = 'problem_attempt' WHERE event_type = 'leetcode'")

    # Migrate LC events → problem_attempts
    op.execute("""
        INSERT INTO problem_attempts (stream_event_id, slug, title, url, difficulty, rating, vod_timestamp)
        SELECT id, platform_id, title, url, status, rating, vod_timestamp
        FROM stream_events
        WHERE event_type = 'problem_attempt' AND platform_id IS NOT NULL
    """)

    # Migrate project events → project_logs
    op.execute("""
        INSERT INTO project_logs (stream_event_id, url, title, description, vod_timestamp)
        SELECT id, url, title, status, vod_timestamp
        FROM stream_events
        WHERE event_type = 'project'
    """)

    # Migrate solution events → solution_posts (all existing ones are from twitch)
    # DISTINCT ON picks the most recent submission per (slug, username) to avoid
    # duplicate constrained values within the same INSERT.
    op.execute("""
        INSERT INTO solution_posts (problem_slug, platform, username, url, vod_timestamp)
        SELECT DISTINCT ON (platform_id, title)
            platform_id, 'twitch', title, url, vod_timestamp
        FROM stream_events
        WHERE event_type = 'solution' AND platform_id IS NOT NULL AND url IS NOT NULL
        ORDER BY platform_id, title, timestamp DESC
    """)

    # Remove solution events from the timeline (viewer actions, not streamer events)
    op.execute("DELETE FROM stream_events WHERE event_type = 'solution'")

    # Add notes column
    op.add_column('stream_events', sa.Column('notes', sa.String(), nullable=True))

    # Migrate ad event durations from platform_id to notes
    op.execute("UPDATE stream_events SET notes = platform_id WHERE event_type = 'ad'")

    # Drop structured columns now held in extension tables
    op.drop_column('stream_events', 'title')
    op.drop_column('stream_events', 'url')
    op.drop_column('stream_events', 'rating')
    op.drop_column('stream_events', 'platform_id')
    op.drop_column('stream_events', 'status')
    op.drop_column('stream_events', 'vod_timestamp')


def downgrade() -> None:
    op.add_column('stream_events', sa.Column('title', sa.String(), nullable=True))
    op.add_column('stream_events', sa.Column('url', sa.String(), nullable=True))
    op.add_column('stream_events', sa.Column('rating', sa.Integer(), nullable=True))
    op.add_column('stream_events', sa.Column('platform_id', sa.String(), nullable=True))
    op.add_column('stream_events', sa.Column('status', sa.String(), nullable=True))
    op.add_column('stream_events', sa.Column('vod_timestamp', sa.String(), nullable=True))
    op.drop_column('stream_events', 'notes')
    op.drop_table('solution_posts')
    op.drop_table('project_logs')
    op.drop_table('problem_attempts')
