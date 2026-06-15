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
