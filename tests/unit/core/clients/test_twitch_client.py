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


def _make_get_sequence(*responses):
    """ClientSession mock whose .get() yields a different (status, json) per call.

    Lets us simulate the 401-then-200 refresh-and-retry flow where the same
    session issues two GETs.
    """
    cms = []
    for status, json_data in responses:
        resp = AsyncMock()
        resp.status = status
        resp.json = AsyncMock(return_value=json_data)
        cm = AsyncMock()
        cm.__aenter__ = AsyncMock(return_value=resp)
        cm.__aexit__ = AsyncMock(return_value=False)
        cms.append(cm)

    mock_http = AsyncMock()
    mock_http.get = MagicMock(side_effect=cms)

    mock_session_cm = AsyncMock()
    mock_session_cm.__aenter__ = AsyncMock(return_value=mock_http)
    mock_session_cm.__aexit__ = AsyncMock(return_value=False)

    return MagicMock(return_value=mock_session_cm)


# ── _get_app_token ──────────────────────────────────────────────────────────

async def test_get_app_token_success_caches_token():
    c = TwitchClient()
    c.app_token = None
    with patch("aiohttp.ClientSession", _make_post_mock(200, {"access_token": "fresh"})):
        token = await c._get_app_token()
    assert token == "fresh"
    assert c.app_token == "fresh"


async def test_get_app_token_non_200_returns_none():
    c = TwitchClient()
    with patch("aiohttp.ClientSession", _make_post_mock(403, {})):
        assert await c._get_app_token() is None


async def test_get_app_token_exception_returns_none():
    c = TwitchClient()
    with patch("aiohttp.ClientSession", side_effect=Exception("network down")):
        assert await c._get_app_token() is None


# ── 401 refresh-and-retry ───────────────────────────────────────────────────

async def test_get_stream_status_refreshes_token_on_401(client):
    live = {"type": "live", "title": "x"}
    refresh = AsyncMock(return_value="new")
    with patch("aiohttp.ClientSession", _make_get_sequence((401, {}), (200, {"data": [live]}))), \
         patch.object(client, "_get_app_token", refresh):
        result = await client.get_stream_status("teststreamer")
    assert result == live
    refresh.assert_awaited_once()


async def test_get_stream_status_401_then_retry_fails_returns_none(client):
    with patch("aiohttp.ClientSession", _make_get_sequence((401, {}), (500, {}))), \
         patch.object(client, "_get_app_token", AsyncMock(return_value="new")):
        assert await client.get_stream_status("teststreamer") is None


async def test_get_stream_status_client_error_propagates(client):
    import aiohttp

    with patch("aiohttp.ClientSession", side_effect=aiohttp.ClientError("boom")):
        with pytest.raises(aiohttp.ClientError):
            await client.get_stream_status("teststreamer")


# ── get_user_id ─────────────────────────────────────────────────────────────

async def test_get_user_id_returns_id(client):
    with patch("aiohttp.ClientSession", _make_aiohttp_mock(200, {"data": [{"id": "999"}]})):
        assert await client.get_user_id("teststreamer") == "999"


async def test_get_user_id_empty_data_returns_none(client):
    with patch("aiohttp.ClientSession", _make_aiohttp_mock(200, {"data": []})):
        assert await client.get_user_id("ghost") is None


async def test_get_user_id_no_token_returns_none():
    c = TwitchClient()
    c.app_token = None
    with patch.object(c, "_get_app_token", AsyncMock(return_value=None)):
        assert await c.get_user_id("x") is None


# ── emotes ──────────────────────────────────────────────────────────────────

async def test_get_global_emotes_builds_cdn_urls(client):
    payload = {"data": [{"name": "Kappa", "id": "25"}]}
    with patch("aiohttp.ClientSession", _make_aiohttp_mock(200, payload)):
        result = await client.get_global_emotes()
    assert result == {"Kappa": "https://static-cdn.jtvnw.net/emoticons/v2/25/default/dark/2.0"}


async def test_get_global_emotes_non_200_returns_empty(client):
    with patch("aiohttp.ClientSession", _make_aiohttp_mock(500, {})):
        assert await client.get_global_emotes() == {}


async def test_get_channel_emotes_empty_broadcaster_short_circuits(client):
    with patch("aiohttp.ClientSession") as cs:
        assert await client.get_channel_emotes("") == {}
    cs.assert_not_called()


async def test_get_channel_emotes_builds_cdn_urls(client):
    payload = {"data": [{"name": "myEmote", "id": "77"}]}
    with patch("aiohttp.ClientSession", _make_aiohttp_mock(200, payload)):
        result = await client.get_channel_emotes("123")
    assert result == {"myEmote": "https://static-cdn.jtvnw.net/emoticons/v2/77/default/dark/2.0"}


# ── followers / subscribers / bits (user-token endpoints) ───────────────────

async def test_get_followers_returns_items_and_cursor(client):
    payload = {"data": [{"user_name": "a"}], "pagination": {"cursor": "next"}}
    with patch("aiohttp.ClientSession", _make_aiohttp_mock(200, payload)):
        items, cursor = await client.get_followers("123", "utok")
    assert items == [{"user_name": "a"}]
    assert cursor == "next"


async def test_get_followers_last_page_cursor_none(client):
    payload = {"data": [{"user_name": "a"}], "pagination": {}}
    with patch("aiohttp.ClientSession", _make_aiohttp_mock(200, payload)):
        items, cursor = await client.get_followers("123", "utok")
    assert cursor is None


async def test_get_followers_non_200_returns_empty(client):
    with patch("aiohttp.ClientSession", _make_aiohttp_mock(401, {})):
        assert await client.get_followers("123", "utok") == ([], None)


async def test_get_followers_passes_after_cursor(client):
    mock_session = _make_aiohttp_mock(200, {"data": [], "pagination": {}})
    with patch("aiohttp.ClientSession", mock_session):
        await client.get_followers("123", "utok", after="CURSOR")
    # The .get URL is the first positional arg of the captured call.
    get_call = mock_session.return_value.__aenter__.return_value.get
    assert "after=CURSOR" in get_call.call_args.args[0]


async def test_get_subscribers_returns_items_and_cursor(client):
    payload = {"data": [{"user_name": "sub"}], "pagination": {"cursor": "c2"}}
    with patch("aiohttp.ClientSession", _make_aiohttp_mock(200, payload)):
        items, cursor = await client.get_subscribers("123", "utok")
    assert items == [{"user_name": "sub"}]
    assert cursor == "c2"


async def test_get_subscribers_non_200_returns_empty(client):
    with patch("aiohttp.ClientSession", _make_aiohttp_mock(403, {})):
        assert await client.get_subscribers("123", "utok") == ([], None)


async def test_get_bits_leaderboard_returns_entries(client):
    payload = {"data": [{"user_name": "whale", "score": 5000}]}
    with patch("aiohttp.ClientSession", _make_aiohttp_mock(200, payload)):
        assert await client.get_bits_leaderboard("123", "utok") == payload["data"]


async def test_get_bits_leaderboard_non_200_returns_empty(client):
    with patch("aiohttp.ClientSession", _make_aiohttp_mock(500, {})):
        assert await client.get_bits_leaderboard("123", "utok") == []


async def test_get_bits_leaderboard_exception_returns_empty(client):
    with patch("aiohttp.ClientSession", side_effect=Exception("boom")):
        assert await client.get_bits_leaderboard("123", "utok") == []
