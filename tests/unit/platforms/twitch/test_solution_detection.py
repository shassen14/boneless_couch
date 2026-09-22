# tests/unit/platforms/twitch/test_solution_detection.py
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from couchd.core.models import ProblemAttempt, ProblemPost, StreamSession
from couchd.platforms.twitch.components.lc_commands import LCCommands

_MOD = "couchd.platforms.twitch.components.lc_commands"

_START_TIME = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def bot_commands():
    return LCCommands(
        lc_client=MagicMock(),
        metrics_tracker=MagicMock(),
        mod_engine=MagicMock(),
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
    db = _mock_db(_problem_post("two-sum"))
    upsert = AsyncMock(return_value=True)
    url = "https://leetcode.com/problems/two-sum/submissions/123456/"

    with (
        patch(f"{_MOD}.get_active_session", AsyncMock(return_value=None)),
        patch(f"{_MOD}.get_session", _make_get_session(db)),
        patch(f"{_MOD}.upsert_solution", upsert),
    ):
        await bot_commands._check_solution_url(_payload(url))

    upsert.assert_awaited_once_with("two-sum", "twitch", "viewer1", url, None)  # no active session


async def test_slug_url_with_active_session_captures_vod_timestamp(bot_commands):
    """When streaming, vod_timestamp is recorded for video editing reference."""
    db = _mock_db(_problem_post("two-sum"))
    upsert = AsyncMock(return_value=True)

    with (
        patch(f"{_MOD}.get_active_session", AsyncMock(return_value=_stream_session())),
        patch(f"{_MOD}.get_session", _make_get_session(db)),
        patch(f"{_MOD}.compute_vod_timestamp", return_value="00h30m00s"),
        patch(f"{_MOD}.upsert_solution", upsert),
    ):
        await bot_commands._check_solution_url(
            _payload("https://leetcode.com/problems/two-sum/submissions/123456/")
        )

    assert upsert.await_args.args[4] == "00h30m00s"


async def test_slug_url_no_forum_post_skips(bot_commands):
    """Problem not in the forum — solution is ignored."""
    db = _mock_db(None)
    upsert = AsyncMock()

    with (
        patch(f"{_MOD}.get_active_session", AsyncMock(return_value=None)),
        patch(f"{_MOD}.get_session", _make_get_session(db)),
        patch(f"{_MOD}.upsert_solution", upsert),
    ):
        await bot_commands._check_solution_url(
            _payload("https://leetcode.com/problems/two-sum/submissions/123456/")
        )

    upsert.assert_not_called()


# ── bare URL tests ────────────────────────────────────────────────────────────

async def test_bare_url_with_active_session_logs_solution(bot_commands):
    """Bare submission URL is accepted when the slug can be resolved from active problem."""
    attempt = MagicMock(spec=ProblemAttempt)
    attempt.slug = "two-sum"
    db = _mock_db(attempt)
    upsert = AsyncMock(return_value=True)

    with (
        patch(f"{_MOD}.get_active_session", AsyncMock(return_value=_stream_session())),
        patch(f"{_MOD}.get_session", _make_get_session(db)),
        patch(f"{_MOD}.compute_vod_timestamp", return_value="00h30m00s"),
        patch(f"{_MOD}.upsert_solution", upsert),
    ):
        await bot_commands._check_solution_url(
            _payload("https://leetcode.com/submissions/detail/999/")
        )

    assert upsert.await_args.args[0] == "two-sum"


async def test_bare_url_no_active_session_skips(bot_commands):
    """Bare URL off-stream is ignored — slug can't be resolved."""
    db = AsyncMock()

    with (
        patch("couchd.platforms.twitch.components.lc_commands.get_active_session", AsyncMock(return_value=None)),
        patch("couchd.platforms.twitch.components.lc_commands.get_session", _make_get_session(db)),
    ):
        await bot_commands._check_solution_url(
            _payload("https://leetcode.com/submissions/detail/999/")
        )

    db.add.assert_not_called()


# ── misc ──────────────────────────────────────────────────────────────────────

async def test_non_lc_url_skips_immediately(bot_commands):
    with patch("couchd.platforms.twitch.components.lc_commands.get_active_session") as mock_get:
        await bot_commands._check_solution_url(_payload("https://github.com/user/repo"))
    mock_get.assert_not_called()
