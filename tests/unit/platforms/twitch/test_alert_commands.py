# tests/unit/platforms/twitch/test_alert_commands.py
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from couchd.platforms.twitch.components.alert_commands import AlertCommands

_MOD = "couchd.platforms.twitch.components.alert_commands"


@pytest.fixture
def cog():
    return AlertCommands()


async def _run(cog, ctx):
    await type(cog).alerts_cmd._callback(cog, ctx)


def _ctx(content, *, broadcaster=True, moderator=False):
    ctx = MagicMock()
    ctx.content = content
    ctx.author.broadcaster = broadcaster
    ctx.author.moderator = moderator
    ctx.reply = AsyncMock()
    return ctx


@pytest.fixture
def veil_mock():
    with patch(f"{_MOD}.veil") as m:
        m.alerts_on = AsyncMock()
        m.alerts_off = AsyncMock()
        m.alerts_audio_on = AsyncMock()
        m.alerts_audio_off = AsyncMock()
        m.clear_alert_queue = AsyncMock()
        yield m


async def test_non_privileged_user_ignored(cog, veil_mock):
    ctx = _ctx("!alerts on", broadcaster=False, moderator=False)
    await _run(cog, ctx)
    veil_mock.alerts_on.assert_not_awaited()
    ctx.reply.assert_not_awaited()


async def test_alerts_on(cog, veil_mock):
    ctx = _ctx("!alerts on")
    await _run(cog, ctx)
    veil_mock.alerts_on.assert_awaited_once()
    ctx.reply.assert_awaited_once_with("Alerts enabled.")


async def test_alerts_off(cog, veil_mock):
    ctx = _ctx("!alerts off", broadcaster=False, moderator=True)
    await _run(cog, ctx)
    veil_mock.alerts_off.assert_awaited_once()
    ctx.reply.assert_awaited_once_with("Alerts disabled.")


async def test_alerts_audio_on(cog, veil_mock):
    ctx = _ctx("!alerts audio on")
    await _run(cog, ctx)
    veil_mock.alerts_audio_on.assert_awaited_once()
    ctx.reply.assert_awaited_once_with("Alert audio enabled.")


async def test_alerts_audio_off(cog, veil_mock):
    ctx = _ctx("!alerts audio off")
    await _run(cog, ctx)
    veil_mock.alerts_audio_off.assert_awaited_once()
    ctx.reply.assert_awaited_once_with("Alert audio disabled.")


async def test_alerts_audio_missing_mode_shows_usage(cog, veil_mock):
    ctx = _ctx("!alerts audio")
    await _run(cog, ctx)
    veil_mock.alerts_audio_on.assert_not_awaited()
    ctx.reply.assert_awaited_once_with("Usage: !alerts audio on | off")


async def test_alerts_clear(cog, veil_mock):
    ctx = _ctx("!alerts clear")
    await _run(cog, ctx)
    veil_mock.clear_alert_queue.assert_awaited_once()
    ctx.reply.assert_awaited_once_with("Alert queue cleared.")


@pytest.mark.parametrize("content", ["!alerts", "!alerts bogus"])
async def test_unknown_subcommand_shows_usage(cog, veil_mock, content):
    ctx = _ctx(content)
    await _run(cog, ctx)
    ctx.reply.assert_awaited_once_with("Usage: !alerts on | off | audio on | off | clear")
