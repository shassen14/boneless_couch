# tests/unit/platforms/twitch/test_cf_command.py
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select

from couchd.core.models import CFProblemAttempt, StreamEvent
from couchd.platforms.twitch.components.cf_commands import CFCommands

_MOD = "couchd.platforms.twitch.components.cf_commands"


@pytest.fixture
def cog():
    return CFCommands()


async def _run(cog, ctx):
    await type(cog).cf_command._callback(cog, ctx)


def _ctx(content, *, broadcaster=False, moderator=False, uid="1"):
    ctx = MagicMock()
    ctx.content = content
    ctx.author.id = uid
    ctx.author.broadcaster = broadcaster
    ctx.author.moderator = moderator
    ctx.reply = AsyncMock()
    return ctx


# ── !cf (show) ────────────────────────────────────────────────────────────────

async def test_show_no_active_session(cog):
    ctx = _ctx("!cf")
    with patch(f"{_MOD}.get_active_session", AsyncMock(return_value=None)):
        await _run(cog, ctx)
    ctx.reply.assert_awaited_once_with("⚠️ No active stream session.")


async def test_show_none_logged(cog, get_session_fn, stream_session):
    ctx = _ctx("!cf")
    with patch(f"{_MOD}.get_active_session", AsyncMock(return_value=stream_session)), \
         patch(f"{_MOD}.get_session", get_session_fn):
        await _run(cog, ctx)
    ctx.reply.assert_awaited_once_with("No Codeforces problem logged yet this stream.")


async def test_show_current(cog, get_session_fn, db_session, stream_session):
    event = StreamEvent(session_id=stream_session.id, event_type="cf_problem")
    db_session.add(event)
    await db_session.flush()
    db_session.add(CFProblemAttempt(
        stream_event_id=event.id, contest_id=1700, index="A",
        title="Factorial", url="https://codeforces.com/problemset/problem/1700/A",
    ))
    await db_session.commit()

    ctx = _ctx("!cf")
    with patch(f"{_MOD}.get_active_session", AsyncMock(return_value=stream_session)), \
         patch(f"{_MOD}.get_session", get_session_fn):
        await _run(cog, ctx)
    ctx.reply.assert_awaited_once_with(
        "Factorial → https://codeforces.com/problemset/problem/1700/A"
    )


# ── !cf <url> (log) ───────────────────────────────────────────────────────────

async def test_log_non_privileged_ignored(cog):
    ctx = _ctx("!cf https://codeforces.com/problemset/problem/1700/A")
    with patch(f"{_MOD}.cf_client") as cf:
        await _run(cog, ctx)
    cf.parse_problem_url.assert_not_called()
    ctx.reply.assert_not_awaited()


async def test_log_invalid_url(cog):
    ctx = _ctx("!cf bogus", broadcaster=True)
    with patch(f"{_MOD}.cf_client") as cf:
        cf.parse_problem_url = MagicMock(return_value=None)
        await _run(cog, ctx)
    ctx.reply.assert_awaited_once_with("❌ Invalid Codeforces problem URL.")


async def test_log_fetch_failure(cog):
    ctx = _ctx("!cf https://codeforces.com/problemset/problem/1700/A", moderator=True)
    with patch(f"{_MOD}.cf_client") as cf:
        cf.parse_problem_url = MagicMock(return_value=(1700, "A"))
        cf.fetch_problem = AsyncMock(return_value=None)
        await _run(cog, ctx)
    ctx.reply.assert_awaited_once_with("❌ Could not fetch problem info from Codeforces.")


async def test_log_persists_and_replies(cog, get_session_fn, db_session, stream_session):
    ctx = _ctx("!cf https://codeforces.com/problemset/problem/1700/A", broadcaster=True)
    with patch(f"{_MOD}.cf_client") as cf, \
         patch(f"{_MOD}.get_active_session", AsyncMock(return_value=stream_session)), \
         patch(f"{_MOD}.get_session", get_session_fn):
        cf.parse_problem_url = MagicMock(return_value=(1700, "A"))
        cf.fetch_problem = AsyncMock(return_value={
            "title": "Factorial", "rating": 800, "tags": ["math", "greedy"],
        })
        cf.problem_url = MagicMock(return_value="https://codeforces.com/problemset/problem/1700/A")
        await _run(cog, ctx)

    rows = (await db_session.execute(select(CFProblemAttempt))).scalars().all()
    assert len(rows) == 1
    assert rows[0].title == "Factorial"
    assert rows[0].contest_id == 1700
    assert rows[0].tags == "math, greedy"
    assert "Factorial" in ctx.reply.call_args.args[0]
    assert "800" in ctx.reply.call_args.args[0]
