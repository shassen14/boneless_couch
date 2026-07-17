# tests/unit/platforms/youtube/test_project_commands.py
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select

from couchd.core.models import ProjectLog, StreamEvent
from couchd.platforms.youtube.components.project_commands import ProjectCommands

_MOD = "couchd.platforms.youtube.components.project_commands"


@pytest.fixture
def cog():
    return ProjectCommands(github_client=MagicMock())


def _ctx(content, *, broadcaster=False, moderator=False, uid="1"):
    ctx = MagicMock()
    ctx.content = content
    ctx.author.id = uid
    ctx.author.broadcaster = broadcaster
    ctx.author.moderator = moderator
    ctx.reply = AsyncMock()
    return ctx


async def test_show_no_active_session(cog):
    ctx = _ctx("!project")
    with patch(f"{_MOD}.get_active_session", AsyncMock(return_value=None)):
        await cog.cmd_project(ctx)
    ctx.reply.assert_awaited_once_with("No active stream session.")


async def test_show_no_project(cog, get_session_fn, stream_session):
    ctx = _ctx("!project")
    with patch(f"{_MOD}.get_active_session", AsyncMock(return_value=stream_session)), \
         patch(f"{_MOD}.get_session", get_session_fn):
        await cog.cmd_project(ctx)
    ctx.reply.assert_awaited_once_with("No project logged yet.")


async def test_show_current_with_description(cog, get_session_fn, db_session, stream_session):
    event = StreamEvent(session_id=stream_session.id, event_type="project")
    db_session.add(event)
    await db_session.flush()
    db_session.add(ProjectLog(stream_event_id=event.id, url="https://github.com/a/b",
                              title="a/b", description="d"))
    await db_session.commit()
    ctx = _ctx("!project")
    with patch(f"{_MOD}.get_active_session", AsyncMock(return_value=stream_session)), \
         patch(f"{_MOD}.get_session", get_session_fn):
        await cog.cmd_project(ctx)
    ctx.reply.assert_awaited_once_with("Now working on: a/b — d")


async def test_log_non_privileged_ignored(cog):
    ctx = _ctx("!project https://github.com/a/b")
    with patch(f"{_MOD}.get_active_session", AsyncMock()) as gas:
        await cog.cmd_project(ctx)
    gas.assert_not_awaited()


async def test_log_invalid_url(cog):
    ctx = _ctx("!project nope", broadcaster=True)
    await cog.cmd_project(ctx)
    ctx.reply.assert_awaited_once_with("Invalid GitHub URL.")


async def test_log_no_session(cog):
    ctx = _ctx("!project https://github.com/a/b", moderator=True)
    with patch(f"{_MOD}.get_active_session", AsyncMock(return_value=None)):
        await cog.cmd_project(ctx)
    ctx.reply.assert_awaited_once_with("No active stream session found in DB.")


async def test_log_persists(cog, get_session_fn, db_session, stream_session):
    cog.github_client.fetch_repo = AsyncMock(return_value="desc")
    ctx = _ctx("!project https://github.com/owner/repo", broadcaster=True)
    with patch(f"{_MOD}.get_active_session", AsyncMock(return_value=stream_session)), \
         patch(f"{_MOD}.get_session", get_session_fn):
        await cog.cmd_project(ctx)
    rows = (await db_session.execute(select(ProjectLog))).scalars().all()
    assert len(rows) == 1 and rows[0].title == "owner/repo"
    ctx.reply.assert_awaited_once_with("Now working on: owner/repo — desc")
