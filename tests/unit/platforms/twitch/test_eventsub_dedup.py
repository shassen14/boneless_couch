# tests/unit/platforms/twitch/test_eventsub_dedup.py
from collections import deque
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from twitchio.ext import commands

from couchd.platforms.twitch.main import TwitchBot

_MOD = "couchd.platforms.twitch.main"


def _dispatch_bot():
    """Real TwitchBot instance (so super().dispatch resolves) without the heavy
    __init__, carrying just the dedup buffer the override touches."""
    bot = TwitchBot.__new__(TwitchBot)
    bot._seen_message_ids = deque(maxlen=8)
    return bot


def test_dispatch_drops_duplicate_message():
    """A message id delivered twice (duplicate sockets) reaches listeners once."""
    bot = _dispatch_bot()
    msg = SimpleNamespace(id="abc")
    with patch.object(commands.Bot, "dispatch") as parent:
        bot.dispatch("message", msg)
        bot.dispatch("message", msg)
    parent.assert_called_once_with("message", msg)


def test_dispatch_passes_distinct_messages():
    bot = _dispatch_bot()
    with patch.object(commands.Bot, "dispatch") as parent:
        bot.dispatch("message", SimpleNamespace(id="a"))
        bot.dispatch("message", SimpleNamespace(id="b"))
    assert parent.call_count == 2


def test_dispatch_never_dedupes_non_message_events():
    """Non-chat events share no id semantics and must always pass through."""
    bot = _dispatch_bot()
    payload = SimpleNamespace(id="same")
    with patch.object(commands.Bot, "dispatch") as parent:
        bot.dispatch("follow", payload)
        bot.dispatch("follow", payload)
    assert parent.call_count == 2


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


def _sub(status, type_, id_):
    return SimpleNamespace(status=status, type=type_, id=id_, delete=AsyncMock())


async def _aiter(items):
    for item in items:
        yield item


async def test_prune_deletes_only_stale_subs_of_our_types():
    """Disconnected subs of our own types are deleted with their owning token;
    enabled subs and foreign types are left untouched."""
    live = _sub("enabled", "channel.chat.message", "live")
    stale_bot = _sub("websocket_disconnected", "channel.chat.message", "s1")
    stale_owner = _sub("websocket_disconnected", "channel.cheer", "s2")
    foreign = _sub("websocket_disconnected", "channel.ban", "x")
    bot = SimpleNamespace(
        _subscription_token_map=lambda: {"channel.chat.message": "BOT", "channel.cheer": "OWNER"},
        fetch_eventsub_subscriptions=AsyncMock(
            return_value=SimpleNamespace(subscriptions=_aiter([live, stale_bot, stale_owner, foreign]))
        ),
    )

    deleted = await TwitchBot._prune_stale_eventsub_subscriptions(bot)

    assert deleted == 2
    live.delete.assert_not_called()
    foreign.delete.assert_not_called()
    stale_bot.delete.assert_awaited_once_with(token_for="BOT")
    stale_owner.delete.assert_awaited_once_with(token_for="OWNER")


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
