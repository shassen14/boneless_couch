# tests/unit/platforms/youtube/test_timers.py
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from couchd.platforms.youtube.components.timers import ChatTimers

_MOD = "couchd.platforms.youtube.components.timers"


def _make(messages, live_chat_id="LIVE"):
    bot = MagicMock()
    bot._live_chat_id = live_chat_id
    bot.chat_client.send_message = AsyncMock()
    with patch(f"{_MOD}.socials.timer_messages", return_value=messages):
        return ChatTimers(bot=bot), bot


def test_start_disabled_without_messages():
    timer, _ = _make([])
    with patch(f"{_MOD}.asyncio.create_task") as ct:
        timer.start()
    ct.assert_not_called()


def test_start_schedules_loop():
    timer, _ = _make(["a"])

    def _drop(coro):
        coro.close()
        return MagicMock()

    with patch(f"{_MOD}.asyncio.create_task", side_effect=_drop) as ct, \
         patch(f"{_MOD}.settings") as s:
        s.CHAT_TIMER_INTERVAL_MINUTES = 10
        timer.start()
    ct.assert_called_once()


async def test_loop_sends_rotating_messages():
    timer, bot = _make(["a", "b"])
    with patch(f"{_MOD}.settings") as s, \
         patch(f"{_MOD}.asyncio.sleep", AsyncMock(side_effect=[None, None, asyncio.CancelledError()])):
        s.CHAT_TIMER_INTERVAL_MINUTES = 1
        with pytest.raises(asyncio.CancelledError):
            await timer._run_loop()
    sent = [c.args[1] for c in bot.chat_client.send_message.await_args_list]
    assert sent == ["a", "b"]


async def test_loop_skips_when_no_live_chat():
    timer, bot = _make(["a"], live_chat_id=None)
    with patch(f"{_MOD}.settings") as s, \
         patch(f"{_MOD}.asyncio.sleep", AsyncMock(side_effect=[None, asyncio.CancelledError()])):
        s.CHAT_TIMER_INTERVAL_MINUTES = 1
        with pytest.raises(asyncio.CancelledError):
            await timer._run_loop()
    bot.chat_client.send_message.assert_not_awaited()
