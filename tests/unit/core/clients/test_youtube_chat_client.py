# tests/unit/core/clients/test_youtube_chat_client.py
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from couchd.core.clients.youtube_chat import YouTubeAPIError, YouTubeChatClient


@pytest.fixture
def client():
    c = YouTubeChatClient(client_secret_file="secret.json", token_file="token.pkl")
    # Pre-load valid creds so _ensure_creds is a no-op (no OAuth/file access).
    creds = MagicMock()
    creds.valid = True
    creds.token = "tok"
    c._creds = creds
    return c


def _resp(status: int, json_data: dict | None = None, text_data: str = ""):
    r = AsyncMock()
    r.status = status
    r.json = AsyncMock(return_value=json_data or {})
    r.text = AsyncMock(return_value=text_data)
    return r


def _cm(resp):
    cm = AsyncMock()
    cm.__aenter__ = AsyncMock(return_value=resp)
    cm.__aexit__ = AsyncMock(return_value=False)
    return cm


def _session_for(method: str, responses: list):
    """Build aiohttp.ClientSession factory whose `method` yields successive responses."""
    http = AsyncMock()
    # MagicMock (not async) so the CM is returned directly, and call_args is inspectable.
    setattr(http, method, MagicMock(side_effect=[_cm(r) for r in responses]))

    session_cm = AsyncMock()
    session_cm.__aenter__ = AsyncMock(return_value=http)
    session_cm.__aexit__ = AsyncMock(return_value=False)
    return MagicMock(return_value=session_cm), http


# ── get_live_chat_id ──────────────────────────────────────────────────────────

async def test_get_live_chat_id_returns_id(client):
    data = {"items": [{"snippet": {"liveChatId": "LIVE99"}}]}
    factory, _ = _session_for("get", [_resp(200, data)])
    with patch("aiohttp.ClientSession", factory):
        assert await client.get_live_chat_id() == "LIVE99"


async def test_get_live_chat_id_no_broadcast_returns_none(client):
    factory, _ = _session_for("get", [_resp(200, {"items": []})])
    with patch("aiohttp.ClientSession", factory):
        assert await client.get_live_chat_id() is None


async def test_get_live_chat_id_http_error_raises(client):
    factory, _ = _session_for("get", [_resp(503, text_data="unavailable")])
    with patch("aiohttp.ClientSession", factory):
        with pytest.raises(YouTubeAPIError) as exc:
            await client.get_live_chat_id()
    assert exc.value.status == 503


def _reauth(client):
    """Stub _ensure_creds that re-installs valid creds, as a real refresh would."""
    async def _do():
        creds = MagicMock()
        creds.valid = True
        creds.token = "tok2"
        client._creds = creds
    return AsyncMock(side_effect=_do)


async def test_get_live_chat_id_retries_after_401(client):
    data = {"items": [{"snippet": {"liveChatId": "LIVE99"}}]}
    factory, _ = _session_for("get", [_resp(401), _resp(200, data)])
    with patch("aiohttp.ClientSession", factory), \
         patch.object(client, "_ensure_creds", _reauth(client)):
        assert await client.get_live_chat_id() == "LIVE99"


async def test_get_live_chat_id_retry_still_failing_raises(client):
    factory, _ = _session_for("get", [_resp(401), _resp(500, text_data="err")])
    with patch("aiohttp.ClientSession", factory), \
         patch.object(client, "_ensure_creds", _reauth(client)):
        with pytest.raises(YouTubeAPIError):
            await client.get_live_chat_id()


# ── poll_messages ─────────────────────────────────────────────────────────────

async def test_poll_messages_parses_response(client):
    data = {
        "items": [{"id": "m1"}],
        "nextPageToken": "TOK",
        "pollingIntervalMillis": "2500",
    }
    factory, _ = _session_for("get", [_resp(200, data)])
    with patch("aiohttp.ClientSession", factory):
        msgs, token, poll_ms = await client.poll_messages("LIVE99")
    assert msgs == [{"id": "m1"}]
    assert token == "TOK"
    assert poll_ms == 2500


async def test_poll_messages_http_error_returns_safe_defaults(client):
    factory, _ = _session_for("get", [_resp(500, text_data="boom")])
    with patch("aiohttp.ClientSession", factory):
        msgs, token, poll_ms = await client.poll_messages("LIVE99", page_token="PREV")
    assert msgs == []
    assert token == "PREV"  # page token preserved so history isn't re-dispatched
    assert poll_ms > 0


# ── send_message ──────────────────────────────────────────────────────────────

async def test_send_message_success(client):
    factory, http = _session_for("post", [_resp(200)])
    with patch("aiohttp.ClientSession", factory):
        assert await client.send_message("LIVE99", "hi") is True
    body = http.post.call_args.kwargs["json"]
    assert body["snippet"]["textMessageDetails"]["messageText"] == "hi"


async def test_send_message_failure(client):
    factory, _ = _session_for("post", [_resp(403, text_data="forbidden")])
    with patch("aiohttp.ClientSession", factory):
        assert await client.send_message("LIVE99", "hi") is False


# ── delete_message ────────────────────────────────────────────────────────────

async def test_delete_message_success(client):
    factory, http = _session_for("delete", [_resp(204)])
    with patch("aiohttp.ClientSession", factory):
        assert await client.delete_message("m1") is True
    assert http.delete.call_args.kwargs["params"] == {"id": "m1"}


async def test_delete_message_failure(client):
    factory, _ = _session_for("delete", [_resp(404)])
    with patch("aiohttp.ClientSession", factory):
        assert await client.delete_message("m1") is False


# ── ban_user ──────────────────────────────────────────────────────────────────

async def test_ban_user_permanent(client):
    factory, http = _session_for("post", [_resp(200)])
    with patch("aiohttp.ClientSession", factory):
        assert await client.ban_user("LIVE99", "chan1") is True
    snippet = http.post.call_args.kwargs["json"]["snippet"]
    assert snippet["type"] == "permanent"
    assert "banDurationSeconds" not in snippet


async def test_ban_user_temporary_sets_duration(client):
    factory, http = _session_for("post", [_resp(200)])
    with patch("aiohttp.ClientSession", factory):
        assert await client.ban_user("LIVE99", "chan1", duration_seconds=300) is True
    snippet = http.post.call_args.kwargs["json"]["snippet"]
    assert snippet["type"] == "temporary"
    assert snippet["banDurationSeconds"] == 300


async def test_ban_user_failure(client):
    factory, _ = _session_for("post", [_resp(403, text_data="no")])
    with patch("aiohttp.ClientSession", factory):
        assert await client.ban_user("LIVE99", "chan1") is False


# ── unban_user ────────────────────────────────────────────────────────────────

async def test_unban_user_success(client):
    factory, http = _session_for("delete", [_resp(204)])
    with patch("aiohttp.ClientSession", factory):
        assert await client.unban_user("ban7") is True
    assert http.delete.call_args.kwargs["params"] == {"id": "ban7"}


async def test_unban_user_failure(client):
    factory, _ = _session_for("delete", [_resp(404)])
    with patch("aiohttp.ClientSession", factory):
        assert await client.unban_user("ban7") is False
