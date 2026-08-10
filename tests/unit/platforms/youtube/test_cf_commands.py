# tests/unit/platforms/youtube/test_cf_commands.py
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select

from couchd.core.clients import codeforces
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
    ctx.reply.assert_awaited_once_with("📌 1A · P → http://cf/1/A")


def _patch_cf_client(resolved):
    """Patch the client module but keep the real describe() formatting."""
    patcher = patch(f"{_MOD}.cf_client")
    cf = patcher.start()
    cf.resolve_problem = AsyncMock(return_value=resolved)
    cf.describe = codeforces.describe
    return patcher, cf


async def test_log_non_privileged_ignored(cog):
    ctx = _ctx("!cf http://cf/1/A")
    patcher, cf = _patch_cf_client(None)
    try:
        await cog.cmd_cf(ctx)
    finally:
        patcher.stop()
    cf.resolve_problem.assert_not_called()


async def test_log_invalid_url(cog):
    ctx = _ctx("!cf bogus", broadcaster=True)
    patcher, _ = _patch_cf_client(None)
    try:
        await cog.cmd_cf(ctx)
    finally:
        patcher.stop()
    ctx.reply.assert_awaited_once_with("❌ Invalid Codeforces problem URL.")


async def test_log_persists(cog, get_session_fn, db_session, stream_session):
    ctx = _ctx("!cf http://cf/1/A", broadcaster=True)
    patcher, _ = _patch_cf_client({
        "contest_id": 1, "index": "A", "url": "http://cf/1/A",
        "title": "P", "rating": 900, "tags": ["dp"],
    })
    try:
        with patch(f"{_MOD}.get_active_session", AsyncMock(return_value=stream_session)), \
             patch(f"{_MOD}.get_session", get_session_fn):
            await cog.cmd_cf(ctx)
    finally:
        patcher.stop()
    rows = (await db_session.execute(select(CFProblemAttempt))).scalars().all()
    assert len(rows) == 1 and rows[0].tags == "dp"
    assert ctx.reply.call_args.args[0] == "✅ CF: 1A · P · 900 → http://cf/1/A"


async def test_log_passes_trailing_text_as_title(cog, get_session_fn, db_session, stream_session):
    """Gym/edu problems carry no API metadata, so the typed title is forwarded."""
    ctx = _ctx("!cf http://cf/gym/1/A My Problem", broadcaster=True)
    patcher, cf = _patch_cf_client({
        "contest_id": 1, "index": "A", "url": "http://cf/gym/1/A",
        "title": "My Problem", "rating": None, "tags": [],
    })
    try:
        with patch(f"{_MOD}.get_active_session", AsyncMock(return_value=stream_session)), \
             patch(f"{_MOD}.get_session", get_session_fn):
            await cog.cmd_cf(ctx)
    finally:
        patcher.stop()
    cf.resolve_problem.assert_awaited_once_with("http://cf/gym/1/A", "My Problem")
    rows = (await db_session.execute(select(CFProblemAttempt))).scalars().all()
    assert len(rows) == 1 and rows[0].title == "My Problem" and rows[0].tags is None
