# tests/unit/platforms/twitch/test_lc_command.py
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select

from couchd.core.models import ProblemAttempt
from couchd.platforms.twitch.components.lc_commands import LCCommands

_MOD = "couchd.platforms.twitch.components.lc_commands"


@pytest.fixture
def cog():
    return LCCommands(lc_client=MagicMock(), metrics_tracker=MagicMock(), mod_engine=MagicMock())


async def _run(cog, ctx):
    """Invoke the !lc command's raw callback, bypassing the twitchio Command wrapper."""
    await type(cog).leetcode_command._callback(cog, ctx)


def _ctx(content, *, broadcaster=False, moderator=False, uid="1"):
    ctx = MagicMock()
    ctx.content = content
    ctx.author.id = uid
    ctx.author.broadcaster = broadcaster
    ctx.author.moderator = moderator
    ctx.reply = AsyncMock()
    return ctx


def _patches(session=None, get_session_fn=None):
    return (
        patch(f"{_MOD}.get_active_session", AsyncMock(return_value=session)),
        patch(f"{_MOD}.get_session", get_session_fn or MagicMock()),
    )


# ── !lc (show current) ────────────────────────────────────────────────────────

async def test_show_no_active_session_warns(cog):
    ctx = _ctx("!lc")
    p1, p2 = _patches(session=None)
    with p1, p2:
        await _run(cog, ctx)
    ctx.reply.assert_awaited_once_with("⚠️ No active stream session.")


async def test_show_returns_current_problem_url(cog, get_session_fn, lc_event, stream_session):
    ctx = _ctx("!lc")
    with patch(f"{_MOD}.get_active_session", AsyncMock(return_value=stream_session)), \
         patch(f"{_MOD}.get_session", get_session_fn):
        await _run(cog, ctx)
    ctx.reply.assert_awaited_once_with(lc_event.url)


async def test_show_no_problem_logged(cog, get_session_fn, stream_session):
    ctx = _ctx("!lc")
    with patch(f"{_MOD}.get_active_session", AsyncMock(return_value=stream_session)), \
         patch(f"{_MOD}.get_session", get_session_fn):
        await _run(cog, ctx)
    ctx.reply.assert_awaited_once_with("No LeetCode problem logged yet.")


async def test_show_respects_cooldown(cog):
    ctx = _ctx("!lc")
    # Second invocation within the window is silently dropped.
    with patch(f"{_MOD}.get_active_session", AsyncMock(return_value=None)):
        await _run(cog, ctx)
        ctx.reply.reset_mock()
        await _run(cog, ctx)
    ctx.reply.assert_not_awaited()


# ── !lc <url> (log new) — authorization & validation ──────────────────────────

async def test_log_rejected_for_non_privileged_user(cog):
    ctx = _ctx("!lc https://leetcode.com/problems/two-sum/", broadcaster=False, moderator=False)
    with patch(f"{_MOD}.get_active_session", AsyncMock()) as gas:
        await _run(cog, ctx)
    ctx.reply.assert_not_awaited()
    gas.assert_not_called()  # bails before touching the DB


async def test_log_invalid_url(cog):
    ctx = _ctx("!lc https://example.com/foo", broadcaster=True)
    await _run(cog, ctx)
    ctx.reply.assert_awaited_once_with("Invalid LeetCode URL.")


async def test_log_no_active_session(cog):
    ctx = _ctx("!lc https://leetcode.com/problems/two-sum/", moderator=True)
    with patch(f"{_MOD}.get_active_session", AsyncMock(return_value=None)):
        await _run(cog, ctx)
    assert "No active stream session" in ctx.reply.await_args[0][0]


async def test_log_fetch_failure(cog, stream_session):
    ctx = _ctx("!lc https://leetcode.com/problems/two-sum/", broadcaster=True)
    cog.lc_client.fetch_problem = AsyncMock(return_value=None)
    with patch(f"{_MOD}.get_active_session", AsyncMock(return_value=stream_session)):
        await _run(cog, ctx)
    ctx.reply.assert_awaited_once_with("❌ Could not fetch problem data from LeetCode.")


async def test_log_success_persists_attempt(cog, get_session_fn, db_session, stream_session):
    ctx = _ctx("!lc https://leetcode.com/problems/two-sum/", broadcaster=True)
    cog.lc_client.fetch_problem = AsyncMock(
        return_value={"id": 1, "title": "Two Sum", "difficulty": "Easy"}
    )
    cog.lc_client.get_rating = MagicMock(return_value=1234.7)

    with patch(f"{_MOD}.get_active_session", AsyncMock(return_value=stream_session)), \
         patch(f"{_MOD}.get_session", get_session_fn), \
         patch(f"{_MOD}.compute_vod_timestamp", return_value="00h10m00s"):
        await _run(cog, ctx)

    rows = (await db_session.execute(select(ProblemAttempt))).scalars().all()
    assert len(rows) == 1
    assert rows[0].slug == "two-sum"
    assert rows[0].rating == 1235  # rounded
    reply = ctx.reply.await_args[0][0]
    assert "1. Two Sum" in reply and "1235" in reply and "00h10m00s" in reply
