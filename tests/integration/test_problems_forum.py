# tests/integration/test_problems_forum.py
#
# Tests the problems forum cog against a real SQLite in-memory database.
# External services (LeetCode API, Discord) are mocked; only the DB layer is real.
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from discord.ext import tasks
from sqlalchemy import select

from couchd.core.models import StreamEvent
from couchd.platforms.discord.cogs.problems import ProblemsWatcherCog


@pytest.fixture
def cog():
    with patch.object(tasks.Loop, "start"):
        return ProblemsWatcherCog(MagicMock())


# ── _build_embed ──────────────────────────────────────────────────────────────

async def test_build_embed_lc_only_shows_attempted(cog, get_session_fn, lc_event):
    with patch("couchd.platforms.discord.cogs.problems.get_session", get_session_fn):
        name, embed, events = await cog._build_embed("two-sum")

    assert name == "1. Two Sum"
    assert embed is not None
    assert embed.title == "1. Two Sum"
    field_names = [f.name for f in embed.fields]
    assert any("Difficulty" in n for n in field_names)
    assert any("Appearances" in n for n in field_names)
    assert any("Status" in n for n in field_names)
    status_field = next(f for f in embed.fields if "Status" in f.name)
    assert "Attempted" in status_field.value
    assert len(events) == 1


async def test_build_embed_with_solution_hides_attempted(cog, get_session_fn, lc_event, db_session):
    solution = StreamEvent(
        session_id=lc_event.session_id,
        event_type="solution",
        title="teststreamer",
        url="https://leetcode.com/submissions/detail/100/",
        platform_id="two-sum",
        vod_timestamp="00h45m00s",
    )
    db_session.add(solution)
    await db_session.commit()

    with patch("couchd.platforms.discord.cogs.problems.get_session", get_session_fn):
        _, embed, _ = await cog._build_embed("two-sum")

    field_names = [f.name for f in embed.fields]
    assert any("Streamer" in n for n in field_names)
    assert not any("Status" in n for n in field_names)


# ── _poll_streamer_solutions ──────────────────────────────────────────────────

async def test_poll_inserts_solution_event(cog, get_session_fn, db_engine, stream_session, lc_event):
    cog.lc_client.fetch_recent_ac_submissions = AsyncMock(
        return_value=[{"id": "999", "titleSlug": "two-sum", "timestamp": "1700000000"}]
    )

    with (
        patch("couchd.platforms.discord.cogs.problems.get_active_session", AsyncMock(return_value=stream_session)),
        patch("couchd.platforms.discord.cogs.problems.get_session", get_session_fn),
        patch("couchd.platforms.discord.cogs.problems.compute_vod_timestamp", return_value="00h55m00s"),
    ):
        await cog._poll_streamer_solutions()

    # Verify the solution row exists in the DB
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
    factory = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)
    async with factory() as verify_session:
        result = await verify_session.execute(
            select(StreamEvent).where(StreamEvent.event_type == "solution")
        )
        solutions = result.scalars().all()

    assert len(solutions) == 1
    assert solutions[0].platform_id == "two-sum"
    assert solutions[0].title == "teststreamer"
    assert "999" in solutions[0].url
    assert solutions[0].vod_timestamp == "00h55m00s"


async def test_poll_does_not_insert_duplicate(cog, get_session_fn, db_engine, stream_session, lc_event, db_session):
    # Pre-insert a solution with the same URL
    existing = StreamEvent(
        session_id=stream_session.id,
        event_type="solution",
        title="teststreamer",
        url="https://leetcode.com/submissions/detail/999/",
        platform_id="two-sum",
        vod_timestamp="00h50m00s",
    )
    db_session.add(existing)
    await db_session.commit()

    cog.lc_client.fetch_recent_ac_submissions = AsyncMock(
        return_value=[{"id": "999", "titleSlug": "two-sum", "timestamp": "1700000000"}]
    )

    with (
        patch("couchd.platforms.discord.cogs.problems.get_active_session", AsyncMock(return_value=stream_session)),
        patch("couchd.platforms.discord.cogs.problems.get_session", get_session_fn),
        patch("couchd.platforms.discord.cogs.problems.compute_vod_timestamp", return_value="01h00m00s"),
    ):
        await cog._poll_streamer_solutions()

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
    factory = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)
    async with factory() as verify_session:
        result = await verify_session.execute(
            select(StreamEvent).where(StreamEvent.event_type == "solution")
        )
        solutions = result.scalars().all()

    assert len(solutions) == 1  # still just the original, no duplicate
