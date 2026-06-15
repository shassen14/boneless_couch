# tests/unit/platforms/youtube/test_cf_commands.py
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select

from couchd.core.models import CFProblemAttempt, StreamEvent
from couchd.platforms.youtube.components.cf_commands import CFCommands

_MOD = "couchd.platforms.youtube.components.cf_commands"


@pytest.fixture
def cog():
    return CFCommands()


def _ctx(content, *, broadcaster=False, moderator=False, uid="1"):
    ctx = MagicMock()
    ctx.content = content
    ctx.author.id = uid
    ctx.author.broadcaster = broadcaster
    ctx.author.moderator = moderator
    ctx.reply = AsyncMock()
    return ctx


async def test_show_no_session(cog):
    ctx = _ctx("!cf")
    with patch(f"{_MOD}.get_active_session", AsyncMock(return_value=None)):
        await cog.cmd_cf(ctx)
    ctx.reply.assert_awaited_once_with("⚠️ No active stream session.")


async def test_show_none_logged(cog, get_session_fn, stream_session):
    ctx = _ctx("!cf")
    with patch(f"{_MOD}.get_active_session", AsyncMock(return_value=stream_session)), \
         patch(f"{_MOD}.get_session", get_session_fn):
        await cog.cmd_cf(ctx)
    ctx.reply.assert_awaited_once_with("No Codeforces problem logged yet this stream.")


async def test_show_current(cog, get_session_fn, db_session, stream_session):
    event = StreamEvent(session_id=stream_session.id, event_type="cf_problem")
    db_session.add(event)
    await db_session.flush()
    db_session.add(CFProblemAttempt(stream_event_id=event.id, contest_id=1, index="A",
                                    title="P", url="http://cf/1/A"))
    await db_session.commit()
    ctx = _ctx("!cf")
    with patch(f"{_MOD}.get_active_session", AsyncMock(return_value=stream_session)), \
         patch(f"{_MOD}.get_session", get_session_fn):
        await cog.cmd_cf(ctx)
    ctx.reply.assert_awaited_once_with("P → http://cf/1/A")


async def test_log_non_privileged_ignored(cog):
    ctx = _ctx("!cf http://cf/1/A")
    with patch(f"{_MOD}.cf_client") as cf:
        await cog.cmd_cf(ctx)
    cf.parse_problem_url.assert_not_called()


async def test_log_invalid_url(cog):
    ctx = _ctx("!cf bogus", broadcaster=True)
    with patch(f"{_MOD}.cf_client") as cf:
        cf.parse_problem_url = MagicMock(return_value=None)
        await cog.cmd_cf(ctx)
    ctx.reply.assert_awaited_once_with("❌ Invalid Codeforces problem URL.")


async def test_log_fetch_failure(cog):
    ctx = _ctx("!cf http://cf/1/A", moderator=True)
    with patch(f"{_MOD}.cf_client") as cf:
        cf.parse_problem_url = MagicMock(return_value=(1, "A"))
        cf.fetch_problem = AsyncMock(return_value=None)
        await cog.cmd_cf(ctx)
    ctx.reply.assert_awaited_once_with("❌ Could not fetch problem info from Codeforces.")


async def test_log_persists(cog, get_session_fn, db_session, stream_session):
    ctx = _ctx("!cf http://cf/1/A", broadcaster=True)
    with patch(f"{_MOD}.cf_client") as cf, \
         patch(f"{_MOD}.get_active_session", AsyncMock(return_value=stream_session)), \
         patch(f"{_MOD}.get_session", get_session_fn):
        cf.parse_problem_url = MagicMock(return_value=(1, "A"))
        cf.fetch_problem = AsyncMock(return_value={"title": "P", "rating": 900, "tags": ["dp"]})
        cf.problem_url = MagicMock(return_value="http://cf/1/A")
        await cog.cmd_cf(ctx)
    rows = (await db_session.execute(select(CFProblemAttempt))).scalars().all()
    assert len(rows) == 1 and rows[0].tags == "dp"
    assert "900" in ctx.reply.call_args.args[0]
