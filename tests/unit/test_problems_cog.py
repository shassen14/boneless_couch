# tests/unit/test_problems_cog.py
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from discord.ext import tasks

from couchd.core.models import StreamEvent, StreamSession
from couchd.platforms.discord.cogs.problems import ProblemsWatcherCog

_START_TIME = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def cog():
    with patch.object(tasks.Loop, "start"):
        return ProblemsWatcherCog(MagicMock())


def _lc(platform_id="two-sum", title="1. Two Sum", status="Easy", rating=None, vod="00h10m00s"):
    e = MagicMock(spec=StreamEvent)
    e.id = 1
    e.event_type = "leetcode"
    e.platform_id = platform_id
    e.title = title
    e.url = f"https://leetcode.com/problems/{platform_id}/"
    e.status = status
    e.rating = rating
    e.vod_timestamp = vod
    return e


def _sol(platform_id="two-sum", title="teststreamer", url="https://leetcode.com/submissions/detail/100/", vod="00h45m00s"):
    e = MagicMock(spec=StreamEvent)
    e.id = 2
    e.event_type = "solution"
    e.platform_id = platform_id
    e.title = title
    e.url = url
    e.vod_timestamp = vod
    return e


def _make_get_session(events):
    """get_session mock that returns events from a single execute call."""
    db = AsyncMock()
    db.execute = AsyncMock(
        return_value=MagicMock(
            scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=events)))
        )
    )
    db.add = MagicMock()
    db.commit = AsyncMock()

    @asynccontextmanager
    async def _gs():
        yield db

    return _gs, db


def _make_poll_db(*scalar_returns):
    """DB mock for _poll_streamer_solutions with sequential execute results."""
    db = AsyncMock()
    db.execute = AsyncMock(
        side_effect=[MagicMock(scalar_one_or_none=MagicMock(return_value=v)) for v in scalar_returns]
    )
    db.add = MagicMock()
    db.commit = AsyncMock()

    @asynccontextmanager
    async def _gs():
        yield db

    return _gs, db


# ── _build_embed ──────────────────────────────────────────────────────────────

async def test_build_embed_no_events_returns_none(cog):
    gs, _ = _make_get_session([])
    with patch("couchd.platforms.discord.cogs.problems.get_session", gs):
        name, embed, events = await cog._build_embed("two-sum")
    assert name is None and embed is None and events == []


async def test_build_embed_lc_only_shows_attempted_status(cog):
    gs, _ = _make_get_session([_lc()])
    with patch("couchd.platforms.discord.cogs.problems.get_session", gs):
        _, embed, _ = await cog._build_embed("two-sum")
    field_names = [f.name for f in embed.fields]
    assert any("Status" in n for n in field_names)
    status_field = next(f for f in embed.fields if "Status" in f.name)
    assert "Attempted" in status_field.value


async def test_build_embed_with_streamer_solution_shows_section(cog):
    gs, _ = _make_get_session([_lc(), _sol(title="teststreamer")])
    with patch("couchd.platforms.discord.cogs.problems.get_session", gs):
        _, embed, _ = await cog._build_embed("two-sum")
    field_names = [f.name for f in embed.fields]
    assert any("Streamer" in n for n in field_names)
    assert not any("Status" in n for n in field_names)


async def test_build_embed_with_community_solution_shows_section(cog):
    gs, _ = _make_get_session([_lc(), _sol(title="viewer123")])
    with patch("couchd.platforms.discord.cogs.problems.get_session", gs):
        _, embed, _ = await cog._build_embed("two-sum")
    field_names = [f.name for f in embed.fields]
    assert any("Community" in n for n in field_names)


async def test_build_embed_appearances_count_in_field_name(cog):
    lc1, lc2 = _lc(), _lc()
    lc2.id = 3
    lc2.vod_timestamp = "01h00m00s"
    gs, _ = _make_get_session([lc1, lc2])
    with patch("couchd.platforms.discord.cogs.problems.get_session", gs):
        _, embed, _ = await cog._build_embed("two-sum")
    appearances_field = next(f for f in embed.fields if "Appearances" in f.name)
    assert "2" in appearances_field.name


async def test_build_embed_thread_name_capped_at_100(cog):
    gs, _ = _make_get_session([_lc(title="A" * 200)])
    with patch("couchd.platforms.discord.cogs.problems.get_session", gs):
        name, _, _ = await cog._build_embed("two-sum")
    assert len(name) <= 100


# ── _resolve_tags ─────────────────────────────────────────────────────────────

def test_resolve_tags_returns_matching_tag(cog):
    easy = MagicMock()
    easy.name = "Easy"
    hard = MagicMock()
    hard.name = "Hard"
    forum = MagicMock()
    forum.available_tags = [easy, hard]
    assert cog._resolve_tags(forum, "Easy") == [easy]


def test_resolve_tags_no_match_returns_empty(cog):
    tag = MagicMock()
    tag.name = "Easy"
    forum = MagicMock()
    forum.available_tags = [tag]
    assert cog._resolve_tags(forum, "Medium") == []


def test_resolve_tags_none_difficulty_returns_empty(cog):
    forum = MagicMock()
    forum.available_tags = [MagicMock()]
    assert cog._resolve_tags(forum, None) == []


# ── _poll_streamer_solutions ──────────────────────────────────────────────────

async def test_poll_no_username_skips_immediately(cog):
    with patch("couchd.platforms.discord.cogs.problems.settings") as mock_s:
        mock_s.LEETCODE_USERNAME = None
        with patch("couchd.platforms.discord.cogs.problems.get_active_session") as mock_get:
            await cog._poll_streamer_solutions()
        mock_get.assert_not_called()


async def test_poll_no_active_session_skips(cog):
    gs, db = _make_poll_db()
    with (
        patch("couchd.platforms.discord.cogs.problems.get_active_session", AsyncMock(return_value=None)),
        patch("couchd.platforms.discord.cogs.problems.get_session", gs),
    ):
        await cog._poll_streamer_solutions()
    db.add.assert_not_called()


async def test_poll_no_lc_event_skips(cog):
    session = MagicMock(spec=StreamSession)
    session.id = 1
    gs, db = _make_poll_db(None)  # no lc event

    with (
        patch("couchd.platforms.discord.cogs.problems.get_active_session", AsyncMock(return_value=session)),
        patch("couchd.platforms.discord.cogs.problems.get_session", gs),
    ):
        await cog._poll_streamer_solutions()
    db.add.assert_not_called()


async def test_poll_matching_submission_inserts_event(cog):
    session = MagicMock(spec=StreamSession)
    session.id = 1
    session.start_time = _START_TIME

    lc = MagicMock(spec=StreamEvent)
    lc.platform_id = "two-sum"

    gs, db = _make_poll_db(lc, None)  # lc found, dedup miss
    cog.lc_client.fetch_recent_ac_submissions = AsyncMock(
        return_value=[{"id": "555", "titleSlug": "two-sum", "timestamp": "1700000000"}]
    )

    with (
        patch("couchd.platforms.discord.cogs.problems.get_active_session", AsyncMock(return_value=session)),
        patch("couchd.platforms.discord.cogs.problems.get_session", gs),
        patch("couchd.platforms.discord.cogs.problems.compute_vod_timestamp", return_value="01h00m00s"),
    ):
        await cog._poll_streamer_solutions()

    db.add.assert_called_once()
    added = db.add.call_args[0][0]
    assert added.event_type == "solution"
    assert "555" in added.url


async def test_poll_duplicate_submission_skips_insert(cog):
    session = MagicMock(spec=StreamSession)
    session.id = 1
    session.start_time = _START_TIME

    lc = MagicMock(spec=StreamEvent)
    lc.platform_id = "two-sum"
    existing = MagicMock(spec=StreamEvent)

    gs, db = _make_poll_db(lc, existing)  # lc found, dedup hit
    cog.lc_client.fetch_recent_ac_submissions = AsyncMock(
        return_value=[{"id": "555", "titleSlug": "two-sum", "timestamp": "1700000000"}]
    )

    with (
        patch("couchd.platforms.discord.cogs.problems.get_active_session", AsyncMock(return_value=session)),
        patch("couchd.platforms.discord.cogs.problems.get_session", gs),
    ):
        await cog._poll_streamer_solutions()

    db.add.assert_not_called()
