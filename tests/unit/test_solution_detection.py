# tests/unit/test_solution_detection.py
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from couchd.core.models import ProblemAttempt, ProblemPost, SolutionPost, StreamEvent, StreamSession
from couchd.platforms.twitch.components.commands import BotCommands

_START_TIME = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def bot_commands():
    return BotCommands(
        bot=MagicMock(),
        lc_client=MagicMock(),
        ad_manager=MagicMock(),
        metrics_tracker=MagicMock(),
        github_client=MagicMock(),
        youtube_client=None,
    )


def _payload(text, name="viewer1", uid="999"):
    p = MagicMock()
    p.text = text
    p.chatter.name = name
    p.chatter.id = uid
    return p


def _stream_session(sid=1):
    s = MagicMock(spec=StreamSession)
    s.id = sid
    s.start_time = _START_TIME
    return s


def _problem_post(slug="two-sum"):
    p = MagicMock(spec=ProblemPost)
    p.platform_id = slug
    return p


def _make_get_session(mock_db):
    @asynccontextmanager
    async def _gs():
        yield mock_db
    return _gs


def _mock_db(*scalar_returns):
    db = AsyncMock()
    db.execute = AsyncMock(
        side_effect=[MagicMock(scalar_one_or_none=MagicMock(return_value=v)) for v in scalar_returns]
    )
    db.add = MagicMock()
    db.commit = AsyncMock()
    return db


# ── slug-bearing URL tests ────────────────────────────────────────────────────

async def test_slug_url_with_forum_post_logs_solution(bot_commands):
    """Any problem with a forum thread can receive a solution, even off-stream."""
    post = _problem_post("two-sum")
    db = _mock_db(post, None)  # post found, no existing solution

    with (
        patch("couchd.platforms.twitch.components.commands.get_active_session", AsyncMock(return_value=None)),
        patch("couchd.platforms.twitch.components.commands.get_session", _make_get_session(db)),
    ):
        await bot_commands._check_solution_url(
            _payload("https://leetcode.com/problems/two-sum/submissions/123456/")
        )

    db.add.assert_called_once()
    added = db.add.call_args[0][0]
    assert added.problem_slug == "two-sum"
    assert "submissions/123456" in added.url
    assert added.vod_timestamp is None  # no active session


async def test_slug_url_with_active_session_captures_vod_timestamp(bot_commands):
    """When streaming, vod_timestamp is recorded for video editing reference."""
    post = _problem_post("two-sum")
    db = _mock_db(post, None)

    with (
        patch("couchd.platforms.twitch.components.commands.get_active_session", AsyncMock(return_value=_stream_session())),
        patch("couchd.platforms.twitch.components.commands.get_session", _make_get_session(db)),
        patch("couchd.platforms.twitch.components.commands.compute_vod_timestamp", return_value="00h30m00s"),
    ):
        await bot_commands._check_solution_url(
            _payload("https://leetcode.com/problems/two-sum/submissions/123456/")
        )

    added = db.add.call_args[0][0]
    assert added.vod_timestamp == "00h30m00s"


async def test_slug_url_no_forum_post_skips(bot_commands):
    """Problem not in the forum — solution is ignored."""
    db = _mock_db(None)

    with (
        patch("couchd.platforms.twitch.components.commands.get_active_session", AsyncMock(return_value=None)),
        patch("couchd.platforms.twitch.components.commands.get_session", _make_get_session(db)),
    ):
        await bot_commands._check_solution_url(
            _payload("https://leetcode.com/problems/two-sum/submissions/123456/")
        )

    db.add.assert_not_called()


async def test_slug_url_updates_existing_solution(bot_commands):
    """Re-submission updates the URL rather than creating a duplicate."""
    post = _problem_post("two-sum")
    existing = MagicMock(spec=SolutionPost)
    db = _mock_db(post, existing)

    with (
        patch("couchd.platforms.twitch.components.commands.get_active_session", AsyncMock(return_value=None)),
        patch("couchd.platforms.twitch.components.commands.get_session", _make_get_session(db)),
    ):
        await bot_commands._check_solution_url(
            _payload("https://leetcode.com/problems/two-sum/submissions/999/")
        )

    db.add.assert_not_called()
    assert "submissions/999" in existing.url


# ── bare URL tests ────────────────────────────────────────────────────────────

async def test_bare_url_with_active_session_logs_solution(bot_commands):
    """Bare submission URL is accepted when the slug can be resolved from active problem."""
    session = _stream_session()
    attempt = MagicMock(spec=ProblemAttempt)
    attempt.slug = "two-sum"
    db = _mock_db(attempt, None)

    with (
        patch("couchd.platforms.twitch.components.commands.get_active_session", AsyncMock(return_value=session)),
        patch("couchd.platforms.twitch.components.commands.get_session", _make_get_session(db)),
        patch("couchd.platforms.twitch.components.commands.compute_vod_timestamp", return_value="00h30m00s"),
    ):
        await bot_commands._check_solution_url(
            _payload("https://leetcode.com/submissions/detail/999/")
        )

    db.add.assert_called_once()


async def test_bare_url_no_active_session_skips(bot_commands):
    """Bare URL off-stream is ignored — slug can't be resolved."""
    db = AsyncMock()

    with (
        patch("couchd.platforms.twitch.components.commands.get_active_session", AsyncMock(return_value=None)),
        patch("couchd.platforms.twitch.components.commands.get_session", _make_get_session(db)),
    ):
        await bot_commands._check_solution_url(
            _payload("https://leetcode.com/submissions/detail/999/")
        )

    db.add.assert_not_called()


# ── misc ──────────────────────────────────────────────────────────────────────

async def test_non_lc_url_skips_immediately(bot_commands):
    with patch("couchd.platforms.twitch.components.commands.get_active_session") as mock_get:
        await bot_commands._check_solution_url(_payload("https://github.com/user/repo"))
    mock_get.assert_not_called()
