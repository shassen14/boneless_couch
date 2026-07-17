# tests/unit/platforms/twitch/test_activity_commands.py
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select

from couchd.core.constants import EventType, TASK_DONE
from couchd.core.models import ProjectLog, StreamEvent
from couchd.platforms.twitch.components.activity_commands import ActivityCommands

_MOD = "couchd.platforms.twitch.components.activity_commands"


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


def _run(cog, name, ctx):
    return type(cog).__dict__[name]._callback(cog, ctx)


async def _add_event(db_session, session_id, event_type, notes):
    db_session.add(StreamEvent(session_id=session_id, event_type=event_type, notes=notes))
    await db_session.commit()


# ── _simple_event_command: show ───────────────────────────────────────────────

async def test_game_show_no_active_session(cog):
    ctx = _ctx("!game")
    with patch(f"{_MOD}.get_active_session", AsyncMock(return_value=None)):
        await _run(cog, "game_command", ctx)
    ctx.reply.assert_awaited_once_with("⚠️ No active stream session.")


async def test_game_show_nothing_logged(cog, get_session_fn, stream_session):
    ctx = _ctx("!game")
    with patch(f"{_MOD}.get_active_session", AsyncMock(return_value=stream_session)), \
         patch(f"{_MOD}.get_session", get_session_fn):
        await _run(cog, "game_command", ctx)
    ctx.reply.assert_awaited_once_with("No now playing logged yet.")


async def test_game_show_latest_value(cog, get_session_fn, db_session, stream_session):
    await _add_event(db_session, stream_session.id, EventType.GAME, "Factorio")
    ctx = _ctx("!game")
    with patch(f"{_MOD}.get_active_session", AsyncMock(return_value=stream_session)), \
         patch(f"{_MOD}.get_session", get_session_fn):
        await _run(cog, "game_command", ctx)
    ctx.reply.assert_awaited_once_with("Now playing: Factorio")


# ── _simple_event_command: log ────────────────────────────────────────────────

async def test_game_log_requires_privilege(cog):
    ctx = _ctx("!game Factorio", broadcaster=False, moderator=False)
    with patch(f"{_MOD}.get_active_session", AsyncMock()) as gas:
        await _run(cog, "game_command", ctx)
    ctx.reply.assert_not_awaited()
    gas.assert_not_called()


async def test_game_log_persists_event(cog, get_session_fn, db_session, stream_session):
    ctx = _ctx("!game  Factorio  ", broadcaster=True)
    with patch(f"{_MOD}.get_active_session", AsyncMock(return_value=stream_session)), \
         patch(f"{_MOD}.get_session", get_session_fn):
        await _run(cog, "game_command", ctx)
    rows = (await db_session.execute(
        select(StreamEvent).where(StreamEvent.event_type == EventType.GAME)
    )).scalars().all()
    assert len(rows) == 1
    assert rows[0].notes == "Factorio"  # trimmed
    ctx.reply.assert_awaited_once_with("✅ Now playing: Factorio")


# ── task_command ──────────────────────────────────────────────────────────────

async def test_task_show_none(cog, get_session_fn, stream_session):
    ctx = _ctx("!task")
    with patch(f"{_MOD}.get_active_session", AsyncMock(return_value=stream_session)), \
         patch(f"{_MOD}.get_session", get_session_fn):
        await _run(cog, "task_command", ctx)
    ctx.reply.assert_awaited_once_with("No active task.")


async def test_task_show_done_treated_as_inactive(cog, get_session_fn, db_session, stream_session):
    await _add_event(db_session, stream_session.id, EventType.TASK, TASK_DONE)
    ctx = _ctx("!task")
    with patch(f"{_MOD}.get_active_session", AsyncMock(return_value=stream_session)), \
         patch(f"{_MOD}.get_session", get_session_fn):
        await _run(cog, "task_command", ctx)
    ctx.reply.assert_awaited_once_with("No active task.")


async def test_task_show_active(cog, get_session_fn, db_session, stream_session):
    await _add_event(db_session, stream_session.id, EventType.TASK, "refactor parser")
    ctx = _ctx("!task")
    with patch(f"{_MOD}.get_active_session", AsyncMock(return_value=stream_session)), \
         patch(f"{_MOD}.get_session", get_session_fn):
        await _run(cog, "task_command", ctx)
    ctx.reply.assert_awaited_once_with("Current task: refactor parser")


async def test_task_set(cog, get_session_fn, stream_session):
    ctx = _ctx("!task write tests", broadcaster=True)
    with patch(f"{_MOD}.get_active_session", AsyncMock(return_value=stream_session)), \
         patch(f"{_MOD}.get_session", get_session_fn):
        await _run(cog, "task_command", ctx)
    ctx.reply.assert_awaited_once_with("✅ Task: write tests")


async def test_task_done_clears(cog, get_session_fn, stream_session):
    ctx = _ctx("!task done", moderator=True)
    with patch(f"{_MOD}.get_active_session", AsyncMock(return_value=stream_session)), \
         patch(f"{_MOD}.get_session", get_session_fn):
        await _run(cog, "task_command", ctx)
    ctx.reply.assert_awaited_once_with("✅ Task cleared.")


# ── status_command ────────────────────────────────────────────────────────────

async def test_status_just_streaming(cog, get_session_fn, stream_session):
    ctx = _ctx("!status")
    with patch(f"{_MOD}.get_active_session", AsyncMock(return_value=stream_session)), \
         patch(f"{_MOD}.get_session", get_session_fn):
        await _run(cog, "status_command", ctx)
    ctx.reply.assert_awaited_once_with("Current Status: Just streaming")


async def test_status_macro_and_task(cog, get_session_fn, db_session, stream_session):
    await _add_event(db_session, stream_session.id, EventType.GAME, "Factorio")
    await _add_event(db_session, stream_session.id, EventType.TASK, "build base")
    ctx = _ctx("!status")
    with patch(f"{_MOD}.get_active_session", AsyncMock(return_value=stream_session)), \
         patch(f"{_MOD}.get_session", get_session_fn):
        await _run(cog, "status_command", ctx)
    ctx.reply.assert_awaited_once_with("Current Status: Playing [Factorio] ➔ Task: build base")


# ── _format_macro ─────────────────────────────────────────────────────────────

async def test_format_macro_project(cog, get_session_fn, db_session, stream_session):
    db_session.add(StreamEvent(id=None, session_id=stream_session.id, event_type=EventType.PROJECT))
    await db_session.flush()
    event = (await db_session.execute(select(StreamEvent))).scalars().first()
    db_session.add(ProjectLog(stream_event_id=event.id, title="couchd", url="u", description="d"))
    await db_session.commit()

    label = await cog._format_macro(db_session, event)
    assert label == "Working on [couchd]"


async def test_format_macro_simple_game(cog, db_session, stream_session):
    event = StreamEvent(session_id=stream_session.id, event_type=EventType.GAME, notes="Celeste")
    db_session.add(event)
    await db_session.commit()
    label = await cog._format_macro(db_session, event)
    assert label == "Playing [Celeste]"
