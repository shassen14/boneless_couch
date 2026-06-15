# tests/unit/platforms/youtube/test_activity_commands.py
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select

from couchd.core.models import ProblemAttempt, ProjectLog, StreamEvent
from couchd.platforms.youtube.components.activity_commands import ActivityCommands

_MOD = "couchd.platforms.youtube.components.activity_commands"


@pytest.fixture
def cog():
    return ActivityCommands()


def _ctx(content, *, broadcaster=False, moderator=False, uid="1"):
    ctx = MagicMock()
    ctx.content = content
    ctx.author.id = uid
    ctx.author.broadcaster = broadcaster
    ctx.author.moderator = moderator
    ctx.reply = AsyncMock()
    return ctx


# ── simple event (game/edit/topic) ────────────────────────────────────────────

async def test_game_show_no_session(cog):
    ctx = _ctx("!game")
    with patch(f"{_MOD}.get_active_session", AsyncMock(return_value=None)):
        await cog.cmd_game(ctx)
    ctx.reply.assert_awaited_once_with("No active stream session.")


async def test_game_show_none_logged(cog, get_session_fn, stream_session):
    ctx = _ctx("!game")
    with patch(f"{_MOD}.get_active_session", AsyncMock(return_value=stream_session)), \
         patch(f"{_MOD}.get_session", get_session_fn):
        await cog.cmd_game(ctx)
    ctx.reply.assert_awaited_once_with("No now playing logged yet.")


async def test_game_log_non_privileged_ignored(cog, stream_session):
    ctx = _ctx("!game Celeste")
    with patch(f"{_MOD}.get_active_session", AsyncMock(return_value=stream_session)):
        await cog.cmd_game(ctx)
    ctx.reply.assert_not_awaited()


async def test_game_log_persists(cog, get_session_fn, db_session, stream_session):
    ctx = _ctx("!game Celeste", broadcaster=True)
    with patch(f"{_MOD}.get_active_session", AsyncMock(return_value=stream_session)), \
         patch(f"{_MOD}.get_session", get_session_fn):
        await cog.cmd_game(ctx)
    rows = (await db_session.execute(
        select(StreamEvent).where(StreamEvent.event_type == "game")
    )).scalars().all()
    assert len(rows) == 1 and rows[0].notes == "Celeste"
    ctx.reply.assert_awaited_once_with("Now playing: Celeste")


async def test_game_log_no_session(cog):
    ctx = _ctx("!game Celeste", moderator=True)
    with patch(f"{_MOD}.get_active_session", AsyncMock(return_value=None)):
        await cog.cmd_game(ctx)
    ctx.reply.assert_awaited_once_with("No active stream session found in DB.")


# ── task ──────────────────────────────────────────────────────────────────────

async def test_task_show_none(cog, get_session_fn, stream_session):
    ctx = _ctx("!task")
    with patch(f"{_MOD}.get_active_session", AsyncMock(return_value=stream_session)), \
         patch(f"{_MOD}.get_session", get_session_fn):
        await cog.cmd_task(ctx)
    ctx.reply.assert_awaited_once_with("No active task.")


async def test_task_set_and_clear(cog, get_session_fn, db_session, stream_session):
    ctx = _ctx("!task write tests", broadcaster=True)
    with patch(f"{_MOD}.get_active_session", AsyncMock(return_value=stream_session)), \
         patch(f"{_MOD}.get_session", get_session_fn):
        await cog.cmd_task(ctx)
    ctx.reply.assert_awaited_with("Task: write tests")

    ctx2 = _ctx("!task done", broadcaster=True)
    with patch(f"{_MOD}.get_active_session", AsyncMock(return_value=stream_session)), \
         patch(f"{_MOD}.get_session", get_session_fn):
        await cog.cmd_task(ctx2)
    ctx2.reply.assert_awaited_with("Task cleared.")


async def test_task_show_active_after_set(cog, get_session_fn, db_session, stream_session):
    db_session.add(StreamEvent(session_id=stream_session.id, event_type="task", notes="refactor"))
    await db_session.commit()
    ctx = _ctx("!task")
    with patch(f"{_MOD}.get_active_session", AsyncMock(return_value=stream_session)), \
         patch(f"{_MOD}.get_session", get_session_fn):
        await cog.cmd_task(ctx)
    ctx.reply.assert_awaited_once_with("Current task: refactor")


# ── status ────────────────────────────────────────────────────────────────────

async def test_status_just_streaming(cog, get_session_fn, stream_session):
    ctx = _ctx("!status")
    with patch(f"{_MOD}.get_active_session", AsyncMock(return_value=stream_session)), \
         patch(f"{_MOD}.get_session", get_session_fn):
        await cog.cmd_status(ctx)
    ctx.reply.assert_awaited_once_with("Status: Just streaming")


async def test_status_with_macro_and_task(cog, get_session_fn, db_session, stream_session):
    db_session.add(StreamEvent(session_id=stream_session.id, event_type="game", notes="Celeste"))
    db_session.add(StreamEvent(session_id=stream_session.id, event_type="task", notes="beat ch1"))
    await db_session.commit()
    ctx = _ctx("!status")
    with patch(f"{_MOD}.get_active_session", AsyncMock(return_value=stream_session)), \
         patch(f"{_MOD}.get_session", get_session_fn):
        await cog.cmd_status(ctx)
    ctx.reply.assert_awaited_once_with("Status: Playing [Celeste] → Task: beat ch1")


async def test_status_macro_problem_attempt(cog, get_session_fn, db_session, stream_session):
    event = StreamEvent(session_id=stream_session.id, event_type="problem_attempt")
    db_session.add(event)
    await db_session.flush()
    db_session.add(ProblemAttempt(stream_event_id=event.id, slug="two-sum",
                                  title="Two Sum", url="http://x"))
    await db_session.commit()
    ctx = _ctx("!status")
    with patch(f"{_MOD}.get_active_session", AsyncMock(return_value=stream_session)), \
         patch(f"{_MOD}.get_session", get_session_fn):
        await cog.cmd_status(ctx)
    ctx.reply.assert_awaited_once_with("Status: Solving [LeetCode: Two Sum]")
