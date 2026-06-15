# tests/unit/platforms/twitch/test_eventsub_dedup.py
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from couchd.platforms.twitch.main import TwitchBot

_MOD = "couchd.platforms.twitch.main"


def _socket(connected, count):
    return SimpleNamespace(connected=connected, subscription_count=count, close=AsyncMock())


async def test_collapse_keeps_one_live_socket_per_token():
    """Two connected sockets for one token must collapse to the most-subscribed one."""
    keep = _socket(connected=True, count=10)
    drop = _socket(connected=True, count=3)
    dead = _socket(connected=False, count=0)  # already-dead: not our concern here
    bot = SimpleNamespace(_websockets={"owner": {"a": keep, "b": drop, "c": dead}})

    closed = await TwitchBot._collapse_duplicate_sockets(bot)

    assert closed == 1
    drop.close.assert_awaited_once()
    keep.close.assert_not_called()


async def test_collapse_noop_with_single_socket():
    only = _socket(connected=True, count=5)
    bot = SimpleNamespace(_websockets={"owner": {"a": only}})

    closed = await TwitchBot._collapse_duplicate_sockets(bot)

    assert closed == 0
    only.close.assert_not_called()


def _online_bot():
    return SimpleNamespace(
        _online_started_at=None,
        twitch_client=SimpleNamespace(get_stream_status_when_ready=AsyncMock(return_value={})),
        ad_scheduler=MagicMock(),
    )


@asynccontextmanager
async def _fake_session():
    yield AsyncMock()


async def test_stream_online_ignores_duplicate_delivery():
    """Two deliveries of the same go-live (identical started_at) fire one opener."""
    bot = _online_bot()
    payload = SimpleNamespace(type="live", started_at=datetime(2026, 6, 15, tzinfo=timezone.utc))

    with patch(f"{_MOD}.send_chat_message", new=AsyncMock()) as send, \
         patch(f"{_MOD}.get_session", _fake_session):
        await TwitchBot.event_stream_online(bot, payload)
        await TwitchBot.event_stream_online(bot, payload)

    send.assert_awaited_once()
    bot.ad_scheduler.fire_opener.assert_called_once()


async def test_stream_online_processes_new_transition_after_offline():
    bot = _online_bot()
    first = SimpleNamespace(type="live", started_at=datetime(2026, 6, 15, tzinfo=timezone.utc))
    second = SimpleNamespace(type="live", started_at=datetime(2026, 6, 16, tzinfo=timezone.utc))

    with patch(f"{_MOD}.send_chat_message", new=AsyncMock()) as send, \
         patch(f"{_MOD}.get_session", _fake_session):
        await TwitchBot.event_stream_online(bot, first)
        await TwitchBot.event_stream_online(bot, second)

    assert send.await_count == 2
