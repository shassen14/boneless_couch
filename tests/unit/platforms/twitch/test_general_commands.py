# tests/unit/platforms/twitch/test_general_commands.py
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select

from couchd.core.models import ClipLog, IdeaPost
from couchd.platforms.twitch.components.general_commands import GeneralCommands

_MOD = "couchd.platforms.twitch.components.general_commands"


@pytest.fixture
def bot():
    return MagicMock()


@pytest.fixture
def cog(bot):
    return GeneralCommands(bot=bot, youtube_client=None)


def _ctx(content, *, broadcaster=False, moderator=False, uid="1", name="viewer"):
    ctx = MagicMock()
    ctx.content = content
    ctx.author.id = uid
    ctx.author.name = name
    ctx.author.display_name = name.title()
    ctx.author.broadcaster = broadcaster
    ctx.author.moderator = moderator
    ctx.reply = AsyncMock()
    ctx.send = AsyncMock()
    return ctx


async def _run(callback, cog, ctx):
    await callback._callback(cog, ctx)


# ── simple replies ────────────────────────────────────────────────────────────

async def test_commands_list_replies_with_docs_link(cog):
    ctx = _ctx("!commands")
    await _run(type(cog).commands_list, cog, ctx)
    assert "docs/twitch-commands.md" in ctx.reply.call_args.args[0]


async def test_commands_list_respects_cooldown(cog):
    ctx = _ctx("!commands")
    await _run(type(cog).commands_list, cog, ctx)
    ctx.reply.reset_mock()
    await _run(type(cog).commands_list, cog, ctx)
    ctx.reply.assert_not_awaited()


# ── newvideo ──────────────────────────────────────────────────────────────────

async def test_newvideo_not_configured(cog):
    ctx = _ctx("!newvideo")
    await _run(type(cog).newvideo_command, cog, ctx)
    ctx.reply.assert_awaited_once_with("YouTube is not configured.")


async def test_newvideo_returns_video(bot):
    yt = MagicMock()
    yt.get_latest_video = AsyncMock(return_value={"title": "Ep 1", "video_url": "http://yt/1"})
    cog = GeneralCommands(bot=bot, youtube_client=yt)
    ctx = _ctx("!newvideo")
    await _run(type(cog).newvideo_command, cog, ctx)
    ctx.reply.assert_awaited_once_with("Ep 1 → http://yt/1")


async def test_newvideo_fetch_failure(bot):
    yt = MagicMock()
    yt.get_latest_video = AsyncMock(return_value=None)
    cog = GeneralCommands(bot=bot, youtube_client=yt)
    ctx = _ctx("!newvideo")
    await _run(type(cog).newvideo_command, cog, ctx)
    ctx.reply.assert_awaited_once_with("Could not fetch the latest video right now.")


# ── socials / discord ─────────────────────────────────────────────────────────

async def test_socials_with_links(cog):
    ctx = _ctx("!socials")
    with patch(f"{_MOD}.socials.format_for_chat", return_value="x | y"):
        await _run(type(cog).socials_command, cog, ctx)
    ctx.reply.assert_awaited_once_with("x | y")


async def test_socials_empty(cog):
    ctx = _ctx("!socials")
    with patch(f"{_MOD}.socials.format_for_chat", return_value=""):
        await _run(type(cog).socials_command, cog, ctx)
    ctx.reply.assert_awaited_once_with("No socials configured yet.")


async def test_discord_with_link(cog):
    ctx = _ctx("!discord")
    with patch(f"{_MOD}.socials.find_by_name", return_value="http://discord.gg/x"):
        await _run(type(cog).discord_command, cog, ctx)
    assert "http://discord.gg/x" in ctx.reply.call_args.args[0]


async def test_discord_no_link(cog):
    ctx = _ctx("!discord")
    with patch(f"{_MOD}.socials.find_by_name", return_value=None):
        await _run(type(cog).discord_command, cog, ctx)
    ctx.reply.assert_awaited_once_with("No Discord link configured yet.")


# ── lurk / unlurk ─────────────────────────────────────────────────────────────

async def test_lurk(cog):
    ctx = _ctx("!lurk", name="bob")
    await _run(type(cog).lurk_command, cog, ctx)
    assert "Bob" in ctx.send.call_args.args[0]


async def test_unlurk(cog):
    ctx = _ctx("!unlurk", name="bob")
    await _run(type(cog).unlurk_command, cog, ctx)
    assert "Bob" in ctx.send.call_args.args[0]


# ── !so shoutout ──────────────────────────────────────────────────────────────

async def test_shoutout_non_privileged_ignored(cog):
    ctx = _ctx("!so someone", broadcaster=False, moderator=False)
    await _run(type(cog).shoutout_command, cog, ctx)
    ctx.reply.assert_not_awaited()
    ctx.send.assert_not_awaited()


async def test_shoutout_missing_arg_shows_usage(cog):
    ctx = _ctx("!so", broadcaster=True)
    await _run(type(cog).shoutout_command, cog, ctx)
    ctx.reply.assert_awaited_once_with("Usage: !so <username>")


async def test_shoutout_user_not_found(cog, bot):
    bot.fetch_users = AsyncMock(return_value=[])
    ctx = _ctx("!so @ghost", broadcaster=True)
    await _run(type(cog).shoutout_command, cog, ctx)
    ctx.reply.assert_awaited_once_with("Could not find user 'ghost'.")


async def test_shoutout_success(cog, bot):
    target = MagicMock()
    target.display_name = "Cool"
    target.name = "cool"
    owner = MagicMock()
    owner.send_shoutout = AsyncMock()
    bot.fetch_users = AsyncMock(side_effect=[[target], [owner]])
    ctx = _ctx("!so cool", moderator=True)
    await _run(type(cog).shoutout_command, cog, ctx)
    owner.send_shoutout.assert_awaited_once()
    assert "twitch.tv/cool" in ctx.send.call_args.args[0]


async def test_shoutout_api_error_replies(cog, bot):
    bot.fetch_users = AsyncMock(side_effect=Exception("boom"))
    ctx = _ctx("!so cool", broadcaster=True)
    await _run(type(cog).shoutout_command, cog, ctx)
    ctx.reply.assert_awaited_once_with("❌ Could not send shoutout to cool.")


# ── !idea ─────────────────────────────────────────────────────────────────────

async def test_idea_missing_text_shows_usage(cog):
    ctx = _ctx("!idea", name="bob")
    await _run(type(cog).idea_command, cog, ctx)
    ctx.reply.assert_awaited_once_with("Usage: !idea <your idea text>")


async def test_idea_persisted(cog, get_session_fn, db_session):
    ctx = _ctx("!idea add a leaderboard", name="bob")
    with patch(f"{_MOD}.get_session", get_session_fn):
        await _run(type(cog).idea_command, cog, ctx)

    rows = (await db_session.execute(select(IdeaPost))).scalars().all()
    assert len(rows) == 1
    assert rows[0].text == "add a leaderboard"
    assert rows[0].submitted_by == "bob"
    assert rows[0].platform == "twitch"


# ── !clip ─────────────────────────────────────────────────────────────────────

async def test_clip_no_active_session(cog):
    ctx = _ctx("!clip", name="bob")
    with patch(f"{_MOD}.get_active_session", AsyncMock(return_value=None)):
        await _run(type(cog).clip_command, cog, ctx)
    ctx.reply.assert_awaited_once_with("⚠️ No active stream session.")


async def test_clip_creates_and_logs(cog, bot, get_session_fn, db_session, stream_session):
    created = MagicMock()
    created.id = "ClipABC"
    user = MagicMock()
    user.create_clip = AsyncMock(return_value=created)
    bot.fetch_users = AsyncMock(return_value=[user])

    ctx = _ctx("!clip Best Moment", name="bob")
    with patch(f"{_MOD}.get_active_session", AsyncMock(return_value=stream_session)), \
         patch(f"{_MOD}.get_session", get_session_fn):
        await _run(type(cog).clip_command, cog, ctx)

    assert "ClipABC" in ctx.reply.call_args.args[0]
    rows = (await db_session.execute(select(ClipLog))).scalars().all()
    assert len(rows) == 1
    assert rows[0].clip_id == "ClipABC"
    assert rows[0].title == "Best Moment"
    assert rows[0].clipped_by == "bob"


async def test_clip_creation_failure_replies(cog, bot, stream_session):
    user = MagicMock()
    user.create_clip = AsyncMock(side_effect=Exception("api down"))
    bot.fetch_users = AsyncMock(return_value=[user])
    ctx = _ctx("!clip", name="bob")
    with patch(f"{_MOD}.get_active_session", AsyncMock(return_value=stream_session)):
        await _run(type(cog).clip_command, cog, ctx)
    ctx.reply.assert_awaited_once_with("❌ Could not create clip.")
