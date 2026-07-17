# tests/unit/platforms/discord/test_streams_cog.py
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from couchd.core.constants import StreamDefaults
from couchd.platforms.discord.cogs.streams import StreamWatcherCog

_GET_SESSION = "couchd.platforms.discord.cogs.streams.get_session"


@pytest.fixture
def cog():
    return StreamWatcherCog(bot=MagicMock())


def _session_yielding(new_id):
    """Mock get_session whose INSERT...RETURNING claim resolves to `new_id`."""
    session = MagicMock()
    claim_result = MagicMock()
    claim_result.scalar_one_or_none = MagicMock(return_value=new_id)
    session.execute = AsyncMock(return_value=claim_result)
    session.get = AsyncMock(return_value=MagicMock())  # row updated on success

    @asynccontextmanager
    async def _cm():
        yield session

    return _cm, session


def _discord_channel():
    channel = MagicMock()
    channel.name = "stream-updates"
    msg = MagicMock()
    msg.id = 111
    thread = MagicMock()
    thread.send = AsyncMock(return_value=MagicMock(id=222))
    msg.create_thread = AsyncMock(return_value=thread)
    channel.send = AsyncMock(return_value=msg)
    return channel


async def test_winning_claim_posts_and_updates(cog):
    get_session_cm, session = _session_yielding(new_id=5)
    channel = _discord_channel()
    cog._get_stream_channel = AsyncMock(return_value=channel)

    with patch(_GET_SESSION, get_session_cm):
        await cog.handle_stream_start({"title": "My Title", "category": "Software"})

    # Posted the go-live announcement exactly once...
    channel.send.assert_awaited_once()
    embed = channel.send.await_args.kwargs["embed"]
    assert "My Title" in embed.description
    # ...and attached message ids to the claimed row.
    session.get.assert_awaited_once()


async def test_lost_claim_does_not_post(cog):
    # new_id is None → another invocation already owns this go-live.
    get_session_cm, session = _session_yielding(new_id=None)
    cog._get_stream_channel = AsyncMock()

    with patch(_GET_SESSION, get_session_cm):
        await cog.handle_stream_start({"title": "My Title", "category": "Software"})

    cog._get_stream_channel.assert_not_called()
    session.get.assert_not_called()


async def test_missing_title_falls_back_to_default(cog):
    get_session_cm, _ = _session_yielding(new_id=7)
    channel = _discord_channel()
    cog._get_stream_channel = AsyncMock(return_value=channel)

    with patch(_GET_SESSION, get_session_cm):
        await cog.handle_stream_start({"title": "", "category": ""})

    embed = channel.send.await_args.kwargs["embed"]
    assert StreamDefaults.TITLE.value in embed.description


# ── _get_stream_channel ───────────────────────────────────────────────────────


def _session_returning(scalar_value):
    """get_session whose single execute().scalar_one_or_none() yields a value."""
    session = MagicMock()
    result = MagicMock()
    result.scalar_one_or_none = MagicMock(return_value=scalar_value)
    session.execute = AsyncMock(return_value=result)
    session.get = AsyncMock(return_value=MagicMock())

    @asynccontextmanager
    async def _cm():
        yield session

    return _cm, session


async def test_get_stream_channel_no_config_returns_none(cog):
    get_session_cm, _ = _session_returning(None)
    with patch(_GET_SESSION, get_session_cm):
        assert await cog._get_stream_channel() is None


async def test_get_stream_channel_resolves_configured_channel(cog):
    config = MagicMock(stream_updates_channel_id=123)
    get_session_cm, _ = _session_returning(config)
    channel = MagicMock(name="chan")
    cog.bot.get_channel = MagicMock(return_value=channel)
    with patch(_GET_SESSION, get_session_cm):
        assert await cog._get_stream_channel() is channel
    cog.bot.get_channel.assert_called_once_with(123)


async def test_get_stream_channel_invisible_channel_returns_none(cog):
    config = MagicMock(stream_updates_channel_id=123)
    get_session_cm, _ = _session_returning(config)
    cog.bot.get_channel = MagicMock(return_value=None)  # bot can't see it
    with patch(_GET_SESSION, get_session_cm):
        assert await cog._get_stream_channel() is None


# ── handle_stream_update ──────────────────────────────────────────────────────


def _session_first(value):
    """get_session whose execute().scalars().first() yields a value."""
    session = MagicMock()
    result = MagicMock()
    result.scalars.return_value.first.return_value = value
    result.scalar_one_or_none = MagicMock(return_value=value)
    session.execute = AsyncMock(return_value=result)
    session.get = AsyncMock(return_value=MagicMock())

    @asynccontextmanager
    async def _cm():
        yield session

    return _cm, session


_RENDER = "couchd.platforms.discord.cogs.streams.render_stream_status"


async def test_handle_stream_update_inactive_session_noops(cog):
    get_session_cm, _ = _session_first(MagicMock(is_active=False))
    cog._get_stream_channel = AsyncMock()
    with patch(_GET_SESSION, get_session_cm), patch(_RENDER, AsyncMock()) as render:
        await cog.handle_stream_update(5)
    render.assert_not_called()
    cog._get_stream_channel.assert_not_called()


async def test_handle_stream_update_missing_session_noops(cog):
    get_session_cm, _ = _session_first(None)
    cog._get_stream_channel = AsyncMock()
    with patch(_GET_SESSION, get_session_cm), patch(_RENDER, AsyncMock()) as render:
        await cog.handle_stream_update(5)
    render.assert_not_called()


async def test_handle_stream_update_renders_non_final(cog):
    get_session_cm, session = _session_first(MagicMock(is_active=True))
    cog._get_stream_channel = AsyncMock(return_value=MagicMock())
    with patch(_GET_SESSION, get_session_cm), patch(_RENDER, AsyncMock(return_value=909)) as render:
        await cog.handle_stream_update(5)
    render.assert_awaited_once()
    assert render.await_args.kwargs["final"] is False
    session.get.assert_awaited()  # persisted the new status message id


async def test_handle_stream_update_no_channel_skips_render(cog):
    get_session_cm, _ = _session_first(MagicMock(is_active=True))
    cog._get_stream_channel = AsyncMock(return_value=None)
    with patch(_GET_SESSION, get_session_cm), patch(_RENDER, AsyncMock()) as render:
        await cog.handle_stream_update(5)
    render.assert_not_called()


# ── handle_stream_end ─────────────────────────────────────────────────────────


_NOTIFY = "couchd.platforms.discord.cogs.streams.content_os_client.notify_session_end"


async def test_handle_stream_end_renders_final_and_notifies(cog):
    ss = MagicMock(id=42, is_active=True)
    get_session_cm, _ = _session_first(ss)
    cog._get_stream_channel = AsyncMock(return_value=MagicMock())
    with patch(_GET_SESSION, get_session_cm), \
         patch(_RENDER, AsyncMock()) as render, \
         patch(_NOTIFY, AsyncMock()) as notify:
        await cog.handle_stream_end(42)
    notify.assert_awaited_once_with(42)
    render.assert_awaited_once()
    assert render.await_args.kwargs["final"] is True


async def test_handle_stream_end_missing_session_skips_everything(cog):
    get_session_cm, _ = _session_first(None)
    with patch(_GET_SESSION, get_session_cm), \
         patch(_RENDER, AsyncMock()) as render, \
         patch(_NOTIFY, AsyncMock()) as notify:
        await cog.handle_stream_end(42)
    notify.assert_not_called()
    render.assert_not_called()


async def test_handle_stream_end_notifies_even_without_channel(cog):
    ss = MagicMock(id=42, is_active=True)
    get_session_cm, _ = _session_first(ss)
    cog._get_stream_channel = AsyncMock(return_value=None)
    with patch(_GET_SESSION, get_session_cm), \
         patch(_RENDER, AsyncMock()) as render, \
         patch(_NOTIFY, AsyncMock()) as notify:
        await cog.handle_stream_end(42)
    notify.assert_awaited_once_with(42)  # content_os handoff not lost
    render.assert_not_called()  # no channel → no recap embed


# ── _startup_live_check (failsafe, independent of pg_notify) ───────────────────


_ACTIVE = "couchd.platforms.discord.cogs.streams.get_active_session"
_TWITCH = "couchd.platforms.discord.cogs.streams.TwitchClient"
_SLEEP = "couchd.platforms.discord.cogs.streams.asyncio.sleep"


@pytest.fixture
def startup_cog():
    cog = StreamWatcherCog(bot=MagicMock())
    cog.bot.wait_until_ready = AsyncMock()
    cog.handle_stream_start = AsyncMock()
    return cog


async def test_startup_skips_when_session_already_active(startup_cog):
    with patch(_ACTIVE, AsyncMock(return_value=MagicMock(id=3))), \
         patch(_SLEEP, AsyncMock()), \
         patch(_TWITCH) as twitch:
        await startup_cog._startup_live_check()
    twitch.assert_not_called()
    startup_cog.handle_stream_start.assert_not_called()


async def test_startup_returns_when_offline(startup_cog):
    client = MagicMock()
    client.get_stream_status = AsyncMock(return_value=None)
    with patch(_ACTIVE, AsyncMock(return_value=None)), \
         patch(_SLEEP, AsyncMock()), \
         patch(_TWITCH, return_value=client):
        await startup_cog._startup_live_check()
    startup_cog.handle_stream_start.assert_not_called()


async def test_startup_creates_session_when_live(startup_cog):
    client = MagicMock()
    client.get_stream_status = AsyncMock(
        return_value={"title": "Live!", "game_name": "Software", "thumbnail_url": "u"}
    )
    with patch(_ACTIVE, AsyncMock(return_value=None)), \
         patch(_SLEEP, AsyncMock()), \
         patch(_TWITCH, return_value=client):
        await startup_cog._startup_live_check()
    startup_cog.handle_stream_start.assert_awaited_once()
    payload = startup_cog.handle_stream_start.await_args.args[0]
    assert payload == {"title": "Live!", "category": "Software", "thumbnail_url": "u"}


# ── pg_notify offline dispatch ────────────────────────────────────────────────


async def test_handle_stream_offline_parses_session_id(cog):
    cog.bot.wait_until_ready = AsyncMock()
    cog.handle_stream_end = AsyncMock()
    await cog._handle_stream_offline('{"session_id": 88}')
    cog.handle_stream_end.assert_awaited_once_with(88)


async def test_handle_stream_offline_empty_payload_passes_none(cog):
    cog.bot.wait_until_ready = AsyncMock()
    cog.handle_stream_end = AsyncMock()
    await cog._handle_stream_offline("")
    cog.handle_stream_end.assert_awaited_once_with(None)


async def test_handle_stream_offline_bad_json_is_swallowed(cog):
    cog.bot.wait_until_ready = AsyncMock()
    cog.handle_stream_end = AsyncMock()
    await cog._handle_stream_offline("{not json")  # must not raise
    cog.handle_stream_end.assert_not_called()
