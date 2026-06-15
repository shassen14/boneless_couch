# tests/unit/platforms/twitch/test_timers.py
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from couchd.platforms.twitch.components.timers import ChatTimers

_MOD = "couchd.platforms.twitch.components.timers"


def _make(messages):
    with patch(f"{_MOD}.socials.timer_messages", return_value=messages):
        return ChatTimers(bot=MagicMock())


def test_start_disabled_without_messages():
    timer = _make([])
    with patch(f"{_MOD}.asyncio.create_task") as ct:
        timer.start()
    ct.assert_not_called()


def test_start_schedules_loop_when_messages_present():
    timer = _make(["promo a"])

    def _drop(coro):
        coro.close()
        return MagicMock()

    with patch(f"{_MOD}.asyncio.create_task", side_effect=_drop) as ct, \
         patch(f"{_MOD}.settings") as s:
        s.CHAT_TIMER_INTERVAL_MINUTES = 10
        timer.start()
    ct.assert_called_once()


async def test_loop_sends_rotating_messages_when_live():
    timer = _make(["a", "b"])
    with patch(f"{_MOD}.settings") as s, \
         patch(f"{_MOD}.get_active_session", AsyncMock(return_value=MagicMock())), \
         patch(f"{_MOD}.send_chat_message", AsyncMock()) as send, \
         patch(f"{_MOD}.asyncio.sleep", AsyncMock(side_effect=[None, None, asyncio.CancelledError()])):
        s.CHAT_TIMER_INTERVAL_MINUTES = 1
        with pytest.raises(asyncio.CancelledError):
            await timer._run_loop()
    assert [c.args[1] for c in send.await_args_list] == ["a", "b"]


async def test_loop_skips_when_offline():
    timer = _make(["a"])
    with patch(f"{_MOD}.settings") as s, \
         patch(f"{_MOD}.get_active_session", AsyncMock(return_value=None)), \
         patch(f"{_MOD}.send_chat_message", AsyncMock()) as send, \
         patch(f"{_MOD}.asyncio.sleep", AsyncMock(side_effect=[None, asyncio.CancelledError()])):
        s.CHAT_TIMER_INTERVAL_MINUTES = 1
        with pytest.raises(asyncio.CancelledError):
            await timer._run_loop()
    send.assert_not_awaited()
