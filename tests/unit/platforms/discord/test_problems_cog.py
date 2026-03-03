# tests/unit/platforms/discord/test_problems_cog.py
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from discord.ext import tasks

from couchd.core.models import ProblemAttempt, SolutionPost, StreamSession
from couchd.platforms.discord.cogs.problems import ProblemsWatcherCog
from couchd.platforms.discord.components.problems_forum import build_problem_embed, resolve_tags

_START_TIME = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

_FORUM_PATCH = "couchd.platforms.discord.components.problems_forum.get_session"


@pytest.fixture
def cog():
    with patch.object(tasks.Loop, "start"):
        return ProblemsWatcherCog(MagicMock())


def _attempt(slug="two-sum", title="1. Two Sum", difficulty="Easy", rating=None, vod="00h10m00s"):
    e = MagicMock(spec=ProblemAttempt)
    e.slug = slug
    e.title = title
    e.url = f"https://leetcode.com/problems/{slug}/"
    e.difficulty = difficulty
    e.rating = rating
    e.vod_timestamp = vod
    return e


def _make_forum_db(attempts, sol_count=0):
    """DB mock for build_problem_embed: first execute returns attempts, second returns sol_count."""
    db = AsyncMock()
    db.execute = AsyncMock(side_effect=[
        MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=attempts)))),
        MagicMock(scalar_one=MagicMock(return_value=sol_count)),
    ])

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


# ── build_problem_embed ───────────────────────────────────────────────────────

async def test_build_embed_no_events_returns_none():
    gs, _ = _make_forum_db([])
    with patch(_FORUM_PATCH, gs):
        name, embed, events = await build_problem_embed("two-sum")
    assert name is None and embed is None and events == []


async def test_build_embed_lc_only_shows_attempted_status():
    gs, _ = _make_forum_db([_attempt()])
    with patch(_FORUM_PATCH, gs):
        _, embed, _ = await build_problem_embed("two-sum")
    field_names = [f.name for f in embed.fields]
    assert any("Status" in n for n in field_names)
    status_field = next(f for f in embed.fields if "Status" in f.name)
    assert "Attempted" in status_field.value


async def test_build_embed_with_solutions_hides_status():
    gs, _ = _make_forum_db([_attempt()], sol_count=1)
    with patch(_FORUM_PATCH, gs):
        _, embed, _ = await build_problem_embed("two-sum")
    field_names = [f.name for f in embed.fields]
    assert not any("Status" in n for n in field_names)


async def test_build_embed_appearances_count_in_field_name():
    a1, a2 = _attempt(), _attempt()
    a2.vod_timestamp = "01h00m00s"
    gs, _ = _make_forum_db([a1, a2])
    with patch(_FORUM_PATCH, gs):
        _, embed, _ = await build_problem_embed("two-sum")
    appearances_field = next(f for f in embed.fields if "Appearances" in f.name)
    assert "2" in appearances_field.name


async def test_build_embed_thread_name_capped_at_100():
    a = _attempt(title="A" * 200)
    gs, _ = _make_forum_db([a])
    with patch(_FORUM_PATCH, gs):
        name, _, _ = await build_problem_embed("two-sum")
    assert len(name) <= 100


# ── resolve_tags ──────────────────────────────────────────────────────────────

def test_resolve_tags_returns_matching_tag():
    easy = MagicMock()
    easy.name = "Easy"
    hard = MagicMock()
    hard.name = "Hard"
    forum = MagicMock()
    forum.available_tags = [easy, hard]
    assert resolve_tags(forum, "Easy") == [easy]


def test_resolve_tags_no_match_returns_empty():
    tag = MagicMock()
    tag.name = "Easy"
    forum = MagicMock()
    forum.available_tags = [tag]
    assert resolve_tags(forum, "Medium") == []


def test_resolve_tags_none_difficulty_returns_empty():
    forum = MagicMock()
    forum.available_tags = [MagicMock()]
    assert resolve_tags(forum, None) == []


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


async def test_poll_no_attempt_skips(cog):
    session = MagicMock(spec=StreamSession)
    session.id = 1
    gs, db = _make_poll_db(None)

    with (
        patch("couchd.platforms.discord.cogs.problems.get_active_session", AsyncMock(return_value=session)),
        patch("couchd.platforms.discord.cogs.problems.get_session", gs),
    ):
        await cog._poll_streamer_solutions()
    db.add.assert_not_called()


async def test_poll_matching_submission_inserts_solution(cog):
    session = MagicMock(spec=StreamSession)
    session.id = 1
    session.start_time = _START_TIME

    attempt = MagicMock(spec=ProblemAttempt)
    attempt.slug = "two-sum"

    gs, db = _make_poll_db(attempt, None)  # attempt found, no existing solution
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
    assert isinstance(added, SolutionPost)
    assert added.problem_slug == "two-sum"
    assert "555" in added.url


async def test_poll_duplicate_submission_skips_insert(cog):
    session = MagicMock(spec=StreamSession)
    session.id = 1
    session.start_time = _START_TIME

    attempt = MagicMock(spec=ProblemAttempt)
    attempt.slug = "two-sum"
    existing = MagicMock(spec=SolutionPost)

    gs, db = _make_poll_db(attempt, existing)  # attempt found, existing solution
    cog.lc_client.fetch_recent_ac_submissions = AsyncMock(
        return_value=[{"id": "555", "titleSlug": "two-sum", "timestamp": "1700000000"}]
    )

    with (
        patch("couchd.platforms.discord.cogs.problems.get_active_session", AsyncMock(return_value=session)),
        patch("couchd.platforms.discord.cogs.problems.get_session", gs),
    ):
        await cog._poll_streamer_solutions()

    db.add.assert_not_called()
