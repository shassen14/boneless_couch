# tests/unit/platforms/twitch/test_cockpit.py
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from couchd.platforms.twitch.components import cockpit

_MOD = "couchd.platforms.twitch.components.cockpit"


@pytest.fixture
def bot():
    b = MagicMock()
    b.fetch_users = AsyncMock(return_value=[MagicMock()])
    return b


async def test_blank_text_is_noop(bot):
    with patch(f"{_MOD}.send_chat_message", AsyncMock()) as send:
        await cockpit.handle_send(bot, "   ")
    send.assert_not_awaited()
    bot.get_command.assert_not_called()


async def test_plain_text_sent_to_chat(bot):
    with patch(f"{_MOD}.send_chat_message", AsyncMock()) as send:
        await cockpit.handle_send(bot, "hello chat")
    send.assert_awaited_once_with(bot, "hello chat")
    bot.get_command.assert_not_called()


async def test_unknown_command_ignored(bot):
    bot.get_command = MagicMock(return_value=None)
    with patch(f"{_MOD}.send_chat_message", AsyncMock()) as send:
        await cockpit.handle_send(bot, "!nope arg")
    bot.get_command.assert_called_once_with("nope")
    send.assert_not_awaited()


async def test_known_command_dispatched_with_broadcaster_context(bot):
    callback = AsyncMock()
    command = MagicMock()
    command.callback = callback
    command.component = MagicMock()
    bot.get_command = MagicMock(return_value=command)

    with patch(f"{_MOD}.send_chat_message", AsyncMock()):
        await cockpit.handle_send(bot, "!lc https://x")

    callback.assert_awaited_once()
    passed_component, ctx = callback.call_args.args
    assert passed_component is command.component
    assert ctx.content == "!lc https://x"
    assert ctx.author.broadcaster is True
    assert ctx.author.moderator is True


async def test_command_name_lowercased(bot):
    command = MagicMock()
    command.callback = AsyncMock()
    bot.get_command = MagicMock(return_value=command)
    with patch(f"{_MOD}.send_chat_message", AsyncMock()):
        await cockpit.handle_send(bot, "!LC")
    bot.get_command.assert_called_once_with("lc")


async def test_command_exception_is_swallowed(bot):
    command = MagicMock()
    command.callback = AsyncMock(side_effect=Exception("boom"))
    bot.get_command = MagicMock(return_value=command)
    with patch(f"{_MOD}.send_chat_message", AsyncMock()):
        await cockpit.handle_send(bot, "!lc")  # must not raise


async def test_cockpit_context_reply_and_send_use_chat(bot):
    with patch(f"{_MOD}.send_chat_message", AsyncMock()) as send:
        ctx = cockpit._CockpitContext(content="x", author=cockpit._CockpitAuthor(id="1"), _bot=bot)
        await ctx.reply("a")
        await ctx.send("b")
    assert send.await_count == 2
