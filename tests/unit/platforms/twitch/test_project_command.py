# tests/unit/platforms/twitch/test_project_command.py
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select

from couchd.core.models import ProjectLog
from couchd.platforms.twitch.components.project_commands import ProjectCommands

_MOD = "couchd.platforms.twitch.components.project_commands"


@pytest.fixture
def cog():
    return ProjectCommands(github_client=MagicMock())


async def _run(cog, ctx):
    await type(cog).project_command._callback(cog, ctx)


def _ctx(content, *, broadcaster=False, moderator=False, uid="1"):
    ctx = MagicMock()
    ctx.content = content
    ctx.author.id = uid
    ctx.author.broadcaster = broadcaster
    ctx.author.moderator = moderator
    ctx.reply = AsyncMock()
    return ctx


# ── !project (show current) ───────────────────────────────────────────────────

async def test_show_no_active_session_warns(cog):
    ctx = _ctx("!project")
    with patch(f"{_MOD}.get_active_session", AsyncMock(return_value=None)):
        await _run(cog, ctx)
    ctx.reply.assert_awaited_once_with("⚠️ No active stream session.")


async def test_show_no_project_logged(cog, get_session_fn, stream_session):
    ctx = _ctx("!project")
    with patch(f"{_MOD}.get_active_session", AsyncMock(return_value=stream_session)), \
         patch(f"{_MOD}.get_session", get_session_fn):
        await _run(cog, ctx)
    ctx.reply.assert_awaited_once_with("No project logged yet.")


async def test_show_returns_title_and_description(cog, get_session_fn, db_session, stream_session):
    from couchd.core.models import StreamEvent

    event = StreamEvent(session_id=stream_session.id, event_type="project")
    db_session.add(event)
    await db_session.flush()
    db_session.add(ProjectLog(
        stream_event_id=event.id, url="https://github.com/a/b",
        title="a/b", description="cool repo",
    ))
    await db_session.commit()

    ctx = _ctx("!project")
    with patch(f"{_MOD}.get_active_session", AsyncMock(return_value=stream_session)), \
         patch(f"{_MOD}.get_session", get_session_fn):
        await _run(cog, ctx)
    ctx.reply.assert_awaited_once_with("Now working on: a/b — cool repo")


async def test_show_respects_cooldown(cog):
    ctx = _ctx("!project")
    with patch(f"{_MOD}.get_active_session", AsyncMock(return_value=None)):
        await _run(cog, ctx)
        ctx.reply.reset_mock()
        await _run(cog, ctx)
    ctx.reply.assert_not_awaited()


# ── !project <url> (log) ──────────────────────────────────────────────────────

async def test_log_rejected_for_non_privileged_user(cog):
    ctx = _ctx("!project https://github.com/a/b", broadcaster=False, moderator=False)
    with patch(f"{_MOD}.get_active_session", AsyncMock()) as gas:
        await _run(cog, ctx)
    gas.assert_not_awaited()
    ctx.reply.assert_not_awaited()


@pytest.mark.parametrize("url", [
    "!project not-a-url",
    "!project https://gitlab.com/a/b",
    "!project https://github.com/onlyowner",
])
async def test_log_invalid_github_url(cog, url):
    ctx = _ctx(url, broadcaster=True)
    await _run(cog, ctx)
    ctx.reply.assert_awaited_once_with("Invalid GitHub URL.")


async def test_log_no_active_session(cog):
    ctx = _ctx("!project https://github.com/a/b", moderator=True)
    with patch(f"{_MOD}.get_active_session", AsyncMock(return_value=None)):
        await _run(cog, ctx)
    ctx.reply.assert_awaited_once_with("⚠️ No active stream session found in DB.")


async def test_log_persists_project_and_replies(cog, get_session_fn, db_session, stream_session):
    cog.github_client.fetch_repo = AsyncMock(return_value="a repo desc")
    ctx = _ctx("!project https://github.com/owner/repo/", broadcaster=True)
    with patch(f"{_MOD}.get_active_session", AsyncMock(return_value=stream_session)), \
         patch(f"{_MOD}.get_session", get_session_fn):
        await _run(cog, ctx)

    ctx.reply.assert_awaited_once_with("Now working on: owner/repo — a repo desc")
    rows = (await db_session.execute(select(ProjectLog))).scalars().all()
    assert len(rows) == 1
    assert rows[0].title == "owner/repo"
    assert rows[0].url == "https://github.com/owner/repo/"


async def test_log_no_description_omits_dash(cog, get_session_fn, stream_session):
    cog.github_client.fetch_repo = AsyncMock(return_value=None)
    ctx = _ctx("!project https://github.com/owner/repo", broadcaster=True)
    with patch(f"{_MOD}.get_active_session", AsyncMock(return_value=stream_session)), \
         patch(f"{_MOD}.get_session", get_session_fn):
        await _run(cog, ctx)
    ctx.reply.assert_awaited_once_with("Now working on: owner/repo")
