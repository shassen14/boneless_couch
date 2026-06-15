# tests/unit/platforms/youtube/test_general_commands.py
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select

from couchd.core.models import IdeaPost
from couchd.platforms.youtube.components.general_commands import GeneralCommands

_MOD = "couchd.platforms.youtube.components.general_commands"


@pytest.fixture
def cog():
    return GeneralCommands(youtube_client=None)


def _ctx(content, *, uid="1", name="viewer"):
    ctx = MagicMock()
    ctx.content = content
    ctx.author.id = uid
    ctx.author.name = name
    ctx.reply = AsyncMock()
    return ctx


async def test_commands_link(cog):
    ctx = _ctx("!commands")
    await cog.cmd_commands(ctx)
    assert "docs/youtube-commands.md" in ctx.reply.call_args.args[0]


async def test_commands_cooldown(cog):
    ctx = _ctx("!commands")
    await cog.cmd_commands(ctx)
    ctx.reply.reset_mock()
    await cog.cmd_commands(ctx)
    ctx.reply.assert_not_awaited()


async def test_newvideo_not_configured(cog):
    ctx = _ctx("!newvideo")
    await cog.cmd_newvideo(ctx)
    ctx.reply.assert_awaited_once_with("YouTube is not configured.")


async def test_newvideo_returns_video():
    yt = MagicMock()
    yt.get_latest_video = AsyncMock(return_value={"title": "Ep", "video_url": "http://y/1"})
    cog = GeneralCommands(youtube_client=yt)
    ctx = _ctx("!newvideo")
    await cog.cmd_newvideo(ctx)
    ctx.reply.assert_awaited_once_with("Ep → http://y/1")


async def test_newvideo_fetch_failure():
    yt = MagicMock()
    yt.get_latest_video = AsyncMock(return_value=None)
    cog = GeneralCommands(youtube_client=yt)
    ctx = _ctx("!newvideo")
    await cog.cmd_newvideo(ctx)
    ctx.reply.assert_awaited_once_with("Could not fetch the latest video right now.")


async def test_socials_empty(cog):
    ctx = _ctx("!socials")
    with patch(f"{_MOD}.socials.format_for_chat", return_value=""):
        await cog.cmd_socials(ctx)
    ctx.reply.assert_awaited_once_with("No socials configured yet.")


async def test_socials_with_links(cog):
    ctx = _ctx("!socials")
    with patch(f"{_MOD}.socials.format_for_chat", return_value="a | b"):
        await cog.cmd_socials(ctx)
    ctx.reply.assert_awaited_once_with("a | b")


async def test_discord_no_link(cog):
    ctx = _ctx("!discord")
    with patch(f"{_MOD}.socials.find_by_name", return_value=None):
        await cog.cmd_discord(ctx)
    ctx.reply.assert_awaited_once_with("No Discord link configured yet.")


async def test_discord_with_link(cog):
    ctx = _ctx("!discord")
    with patch(f"{_MOD}.socials.find_by_name", return_value="http://d/x"):
        await cog.cmd_discord(ctx)
    assert "http://d/x" in ctx.reply.call_args.args[0]


async def test_idea_usage(cog):
    ctx = _ctx("!idea")
    await cog.cmd_idea(ctx)
    ctx.reply.assert_awaited_once_with("Usage: !idea <your idea text>")


async def test_idea_persisted(cog, get_session_fn, db_session):
    ctx = _ctx("!idea more streams", name="bob")
    with patch(f"{_MOD}.get_session", get_session_fn):
        await cog.cmd_idea(ctx)
    rows = (await db_session.execute(select(IdeaPost))).scalars().all()
    assert len(rows) == 1
    assert rows[0].text == "more streams"
    assert rows[0].platform == "youtube"
    assert rows[0].submitted_by == "bob"
