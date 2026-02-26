# tests/unit/test_solution_detection.py
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from couchd.core.models import StreamEvent, StreamSession
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


def _lc_event(platform_id="two-sum"):
    e = MagicMock(spec=StreamEvent)
    e.platform_id = platform_id
    return e


def _make_get_session(mock_db):
    @asynccontextmanager
    async def _gs():
        yield mock_db
    return _gs


def _mock_db(*scalar_returns):
    """Build a mock DB session whose execute() returns each value in order."""
    db = AsyncMock()
    db.execute = AsyncMock(
        side_effect=[MagicMock(scalar_one_or_none=MagicMock(return_value=v)) for v in scalar_returns]
    )
    db.add = MagicMock()
    db.commit = AsyncMock()
    return db


# ── tests ────────────────────────────────────────────────────────────────────

async def test_pattern_a_slug_match_logs_solution(bot_commands):
    session = _stream_session()
    lc = _lc_event("two-sum")
    db = _mock_db(lc, None)  # lc query hit, dedup miss

    with (
        patch("couchd.platforms.twitch.components.commands.get_active_session", AsyncMock(return_value=session)),
        patch("couchd.platforms.twitch.components.commands.get_session", _make_get_session(db)),
        patch("couchd.platforms.twitch.components.commands.compute_vod_timestamp", return_value="00h30m00s"),
    ):
        await bot_commands._check_solution_url(
            _payload("https://leetcode.com/problems/two-sum/submissions/123456/")
        )

    db.add.assert_called_once()
    added = db.add.call_args[0][0]
    assert added.event_type == "solution"
    assert added.platform_id == "two-sum"
    assert "two-sum/submissions/123456" in added.url


async def test_pattern_a_wrong_slug_skips(bot_commands):
    session = _stream_session()
    lc = _lc_event("add-two-numbers")  # different problem active
    db = _mock_db(lc)

    with (
        patch("couchd.platforms.twitch.components.commands.get_active_session", AsyncMock(return_value=session)),
        patch("couchd.platforms.twitch.components.commands.get_session", _make_get_session(db)),
    ):
        await bot_commands._check_solution_url(
            _payload("https://leetcode.com/problems/two-sum/submissions/123456/")
        )

    db.add.assert_not_called()


async def test_pattern_b_bare_url_logs_solution(bot_commands):
    session = _stream_session()
    lc = _lc_event("two-sum")
    db = _mock_db(lc, None)

    with (
        patch("couchd.platforms.twitch.components.commands.get_active_session", AsyncMock(return_value=session)),
        patch("couchd.platforms.twitch.components.commands.get_session", _make_get_session(db)),
        patch("couchd.platforms.twitch.components.commands.compute_vod_timestamp", return_value="00h30m00s"),
    ):
        await bot_commands._check_solution_url(
            _payload("solved: https://leetcode.com/submissions/detail/999/")
        )

    db.add.assert_called_once()
    added = db.add.call_args[0][0]
    assert added.event_type == "solution"
    assert "submissions/detail/999" in added.url


async def test_non_lc_url_skips_immediately(bot_commands):
    with patch("couchd.platforms.twitch.components.commands.get_active_session") as mock_get:
        await bot_commands._check_solution_url(_payload("https://github.com/user/repo"))
    mock_get.assert_not_called()


async def test_no_active_session_skips(bot_commands):
    db = AsyncMock()
    db.add = MagicMock()

    with (
        patch("couchd.platforms.twitch.components.commands.get_active_session", AsyncMock(return_value=None)),
        patch("couchd.platforms.twitch.components.commands.get_session", _make_get_session(db)),
    ):
        await bot_commands._check_solution_url(
            _payload("https://leetcode.com/problems/two-sum/submissions/1/")
        )

    db.add.assert_not_called()


async def test_no_active_lc_event_skips(bot_commands):
    session = _stream_session()
    db = _mock_db(None)  # no lc event in session

    with (
        patch("couchd.platforms.twitch.components.commands.get_active_session", AsyncMock(return_value=session)),
        patch("couchd.platforms.twitch.components.commands.get_session", _make_get_session(db)),
    ):
        await bot_commands._check_solution_url(
            _payload("https://leetcode.com/problems/two-sum/submissions/1/")
        )

    db.add.assert_not_called()


async def test_duplicate_url_skips(bot_commands):
    session = _stream_session()
    lc = _lc_event("two-sum")
    existing = MagicMock(spec=StreamEvent)
    db = _mock_db(lc, existing)  # lc found, dedup found

    with (
        patch("couchd.platforms.twitch.components.commands.get_active_session", AsyncMock(return_value=session)),
        patch("couchd.platforms.twitch.components.commands.get_session", _make_get_session(db)),
    ):
        await bot_commands._check_solution_url(
            _payload("https://leetcode.com/problems/two-sum/submissions/1/")
        )

    db.add.assert_not_called()
