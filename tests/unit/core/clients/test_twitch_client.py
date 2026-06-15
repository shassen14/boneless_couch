# tests/unit/core/clients/test_twitch_client.py
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from couchd.core.clients.twitch import TwitchClient


@pytest.fixture
def client():
    c = TwitchClient()
    c.app_token = "tok"  # pre-set to skip _get_app_token in most tests
    return c


def _make_aiohttp_mock(status: int, json_data: dict):
    mock_resp = AsyncMock()
    mock_resp.status = status
    mock_resp.json = AsyncMock(return_value=json_data)

    mock_get_cm = AsyncMock()
    mock_get_cm.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_get_cm.__aexit__ = AsyncMock(return_value=False)

    mock_http = AsyncMock()
    mock_http.get = MagicMock(return_value=mock_get_cm)

    mock_session_cm = AsyncMock()
    mock_session_cm.__aenter__ = AsyncMock(return_value=mock_http)
    mock_session_cm.__aexit__ = AsyncMock(return_value=False)

    return MagicMock(return_value=mock_session_cm)


def _make_post_mock(status: int, json_data: dict):
    """Mock for _get_app_token (POST request)."""
    mock_resp = AsyncMock()
    mock_resp.status = status
    mock_resp.json = AsyncMock(return_value=json_data)
    mock_resp.text = AsyncMock(return_value="error")

    mock_post_cm = AsyncMock()
    mock_post_cm.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_post_cm.__aexit__ = AsyncMock(return_value=False)

    mock_http = AsyncMock()
    mock_http.post = MagicMock(return_value=mock_post_cm)

    mock_session_cm = AsyncMock()
    mock_session_cm.__aenter__ = AsyncMock(return_value=mock_http)
    mock_session_cm.__aexit__ = AsyncMock(return_value=False)

    return MagicMock(return_value=mock_session_cm)


# ── get_stream_status ─────────────────────────────────────────────────────────

async def test_get_stream_status_live_returns_stream_data(client):
    stream_data = {"user_login": "teststreamer", "type": "live"}
    mock_session = _make_aiohttp_mock(200, {"data": [stream_data]})

    with patch("aiohttp.ClientSession", mock_session):
        result = await client.get_stream_status("teststreamer")

    assert result == stream_data


async def test_get_stream_status_offline_returns_none(client):
    mock_session = _make_aiohttp_mock(200, {"data": []})

    with patch("aiohttp.ClientSession", mock_session):
        result = await client.get_stream_status("teststreamer")

    assert result is None


async def test_get_stream_status_non_200_returns_none(client):
    mock_session = _make_aiohttp_mock(500, {})

    with patch("aiohttp.ClientSession", mock_session):
        result = await client.get_stream_status("teststreamer")

    assert result is None


async def test_get_stream_status_no_token_returns_none():
    client = TwitchClient()
    client.app_token = None
    mock_session = _make_post_mock(500, {})  # token fetch fails

    with patch("aiohttp.ClientSession", mock_session):
        result = await client.get_stream_status("teststreamer")

    assert result is None


# ── get_clip ──────────────────────────────────────────────────────────────────

async def test_get_clip_returns_clip_data(client):
    clip_data = {"id": "clip123", "url": "https://clips.twitch.tv/clip123"}
    mock_session = _make_aiohttp_mock(200, {"data": [clip_data]})

    with patch("aiohttp.ClientSession", mock_session):
        result = await client.get_clip("clip123")

    assert result == clip_data


async def test_get_clip_non_200_returns_none(client):
    mock_session = _make_aiohttp_mock(404, {})

    with patch("aiohttp.ClientSession", mock_session):
        result = await client.get_clip("clip123")

    assert result is None


# ── get_stream_status_when_ready (propagation tolerance) ───────────────────────

async def test_when_ready_returns_immediately_when_title_present(client):
    live = {"type": "live", "title": "Real Title", "game_name": "Software"}
    client.get_stream_status = AsyncMock(return_value=live)

    with patch("couchd.core.clients.twitch.asyncio.sleep", AsyncMock()) as sleep:
        result = await client.get_stream_status_when_ready("teststreamer")

    assert result == live
    sleep.assert_not_called()  # no waiting when data is already there


async def test_when_ready_polls_until_title_propagates(client):
    live = {"type": "live", "title": "Real Title"}
    # First poll: stream not in Helix yet. Second: live but title still empty.
    # Third: fully propagated.
    client.get_stream_status = AsyncMock(side_effect=[None, {"title": ""}, live])

    with patch("couchd.core.clients.twitch.asyncio.sleep", AsyncMock()) as sleep:
        result = await client.get_stream_status_when_ready("teststreamer")

    assert result == live
    assert sleep.await_count == 2  # slept after the two unready polls


async def test_when_ready_tolerates_transient_errors(client):
    import aiohttp

    live = {"type": "live", "title": "Real Title"}
    client.get_stream_status = AsyncMock(side_effect=[aiohttp.ClientError(), live])

    with patch("couchd.core.clients.twitch.asyncio.sleep", AsyncMock()):
        result = await client.get_stream_status_when_ready("teststreamer")

    assert result == live


async def test_when_ready_returns_last_seen_after_budget_exhausted(client):
    titleless = {"type": "live", "title": ""}
    client.get_stream_status = AsyncMock(return_value=titleless)

    with patch("couchd.core.clients.twitch.asyncio.sleep", AsyncMock()):
        result = await client.get_stream_status_when_ready("teststreamer")

    # Never got a title, but returns the best payload it saw rather than None.
    assert result == titleless
