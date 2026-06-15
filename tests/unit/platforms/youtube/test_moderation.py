# tests/unit/platforms/youtube/test_moderation.py
from unittest.mock import AsyncMock, MagicMock

import pytest

from couchd.platforms.youtube.components.moderation import ModerationCommands


@pytest.fixture
def chat_client():
    c = MagicMock()
    c.delete_message = AsyncMock(return_value=True)
    c.ban_user = AsyncMock(return_value=True)
    c.unban_user = AsyncMock(return_value=True)
    return c


@pytest.fixture
def cog(chat_client):
    return ModerationCommands(chat_client=chat_client)


def _ctx(content, *, broadcaster=False, moderator=False):
    ctx = MagicMock()
    ctx.content = content
    ctx.author.name = "mod"
    ctx.author.broadcaster = broadcaster
    ctx.author.moderator = moderator
    ctx._live_chat_id = "LIVE123"
    ctx.reply = AsyncMock()
    return ctx


# ── privilege gating ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("method,content", [
    ("cmd_delete", "!delete m1"),
    ("cmd_timeout", "!timeout c1 60"),
    ("cmd_ban", "!ban c1"),
    ("cmd_unban", "!unban b1"),
])
async def test_non_privileged_ignored(cog, chat_client, method, content):
    ctx = _ctx(content, broadcaster=False, moderator=False)
    await getattr(cog, method)(ctx)
    ctx.reply.assert_not_awaited()
    chat_client.delete_message.assert_not_awaited()
    chat_client.ban_user.assert_not_awaited()
    chat_client.unban_user.assert_not_awaited()


# ── delete ────────────────────────────────────────────────────────────────────

async def test_delete_usage(cog):
    ctx = _ctx("!delete", moderator=True)
    await cog.cmd_delete(ctx)
    ctx.reply.assert_awaited_once_with("Usage: !delete <message_id>")


async def test_delete_success(cog, chat_client):
    ctx = _ctx("!delete msg42", broadcaster=True)
    await cog.cmd_delete(ctx)
    chat_client.delete_message.assert_awaited_once_with("msg42")
    ctx.reply.assert_not_awaited()


async def test_delete_failure_replies(cog, chat_client):
    chat_client.delete_message = AsyncMock(return_value=False)
    ctx = _ctx("!delete msg42", moderator=True)
    await cog.cmd_delete(ctx)
    ctx.reply.assert_awaited_once_with("Failed to delete message.")


# ── timeout ───────────────────────────────────────────────────────────────────

async def test_timeout_usage(cog):
    ctx = _ctx("!timeout c1", moderator=True)
    await cog.cmd_timeout(ctx)
    ctx.reply.assert_awaited_once_with("Usage: !timeout <channel_id> <seconds>")


async def test_timeout_non_numeric_duration(cog):
    ctx = _ctx("!timeout c1 abc", moderator=True)
    await cog.cmd_timeout(ctx)
    ctx.reply.assert_awaited_once_with("Duration must be a number of seconds.")


async def test_timeout_success(cog, chat_client):
    ctx = _ctx("!timeout chan9 300", broadcaster=True)
    await cog.cmd_timeout(ctx)
    chat_client.ban_user.assert_awaited_once_with("LIVE123", "chan9", 300)
    ctx.reply.assert_not_awaited()


async def test_timeout_failure_replies(cog, chat_client):
    chat_client.ban_user = AsyncMock(return_value=False)
    ctx = _ctx("!timeout chan9 300", moderator=True)
    await cog.cmd_timeout(ctx)
    ctx.reply.assert_awaited_once_with("Failed to timeout user.")


# ── ban / unban ───────────────────────────────────────────────────────────────

async def test_ban_usage(cog):
    ctx = _ctx("!ban", moderator=True)
    await cog.cmd_ban(ctx)
    ctx.reply.assert_awaited_once_with("Usage: !ban <channel_id>")


async def test_ban_success(cog, chat_client):
    ctx = _ctx("!ban chan9", broadcaster=True)
    await cog.cmd_ban(ctx)
    chat_client.ban_user.assert_awaited_once_with("LIVE123", "chan9", duration_seconds=None)


async def test_unban_usage(cog):
    ctx = _ctx("!unban", moderator=True)
    await cog.cmd_unban(ctx)
    ctx.reply.assert_awaited_once_with("Usage: !unban <ban_id>")


async def test_unban_success(cog, chat_client):
    ctx = _ctx("!unban ban7", moderator=True)
    await cog.cmd_unban(ctx)
    chat_client.unban_user.assert_awaited_once_with("ban7")


async def test_unban_failure_replies(cog, chat_client):
    chat_client.unban_user = AsyncMock(return_value=False)
    ctx = _ctx("!unban ban7", moderator=True)
    await cog.cmd_unban(ctx)
    ctx.reply.assert_awaited_once_with("Failed to unban.")
