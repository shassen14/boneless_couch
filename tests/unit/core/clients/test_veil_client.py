# tests/unit/core/clients/test_veil_client.py
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest

from couchd.core.clients import veil

_MOD = "couchd.core.clients.veil"


def _make_post_mock(status: int = 200):
    """Build an aiohttp.ClientSession mock and the captured .post mock."""
    mock_resp = AsyncMock()
    mock_resp.status = status

    mock_req_cm = AsyncMock()
    mock_req_cm.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_req_cm.__aexit__ = AsyncMock(return_value=False)

    mock_http = AsyncMock()
    post = MagicMock(return_value=mock_req_cm)
    mock_http.post = post

    mock_session_cm = AsyncMock()
    mock_session_cm.__aenter__ = AsyncMock(return_value=mock_http)
    mock_session_cm.__aexit__ = AsyncMock(return_value=False)

    return MagicMock(return_value=mock_session_cm), post


@pytest.fixture
def veil_settings():
    """Patch the veil module's settings with controllable URL/secret."""
    s = MagicMock()
    s.VEIL_URL = "http://veil.local"
    s.VEIL_SECRET = "shh"
    with patch(f"{_MOD}.settings", s):
        yield s


# ── post_event ────────────────────────────────────────────────────────────────

async def test_post_event_no_url_is_noop(veil_settings):
    veil_settings.VEIL_URL = ""
    with patch("aiohttp.ClientSession") as cs:
        await veil.post_event("follow", {"user": "x"})
    cs.assert_not_called()


async def test_post_event_sends_payload_and_auth_header(veil_settings):
    session_mock, post = _make_post_mock(200)
    with patch("aiohttp.ClientSession", session_mock):
        await veil.post_event("follow", {"user": "x"})

    post.assert_called_once()
    args, kwargs = post.call_args
    assert args[0] == "http://veil.local/event"
    assert kwargs["json"] == {"type": "follow", "payload": {"user": "x"}}
    assert kwargs["headers"]["Authorization"] == "Bearer shh"


async def test_post_event_without_secret_omits_auth(veil_settings):
    veil_settings.VEIL_SECRET = ""
    session_mock, post = _make_post_mock(204)
    with patch("aiohttp.ClientSession", session_mock):
        await veil.post_event("sub", {})

    assert "Authorization" not in post.call_args.kwargs["headers"]


async def test_post_event_connector_error_is_swallowed(veil_settings):
    with patch("aiohttp.ClientSession", side_effect=aiohttp.ClientConnectorError(MagicMock(), OSError())):
        await veil.post_event("follow", {})  # must not raise


async def test_post_event_generic_error_is_swallowed(veil_settings):
    with patch("aiohttp.ClientSession", side_effect=Exception("boom")):
        await veil.post_event("follow", {})  # must not raise


# ── alert helpers (thin wrappers over _post) ──────────────────────────────────

@pytest.mark.parametrize(
    "fn,path",
    [
        (veil.alerts_on, "/alerts/on"),
        (veil.alerts_off, "/alerts/off"),
        (veil.alerts_audio_on, "/alerts/audio/on"),
        (veil.alerts_audio_off, "/alerts/audio/off"),
        (veil.clear_alert_queue, "/alerts/queue/clear"),
    ],
)
async def test_alert_helpers_post_expected_path(veil_settings, fn, path):
    session_mock, post = _make_post_mock(200)
    with patch("aiohttp.ClientSession", session_mock):
        await fn()

    assert post.call_args.args[0] == f"http://veil.local{path}"


async def test_post_helper_no_url_is_noop(veil_settings):
    veil_settings.VEIL_URL = ""
    with patch("aiohttp.ClientSession") as cs:
        await veil.alerts_on()
    cs.assert_not_called()


async def test_post_helper_error_is_swallowed(veil_settings):
    with patch("aiohttp.ClientSession", side_effect=Exception("boom")):
        await veil.alerts_on()  # must not raise


# ── listen_decisions WS dispatch ──────────────────────────────────────────────


class _WSMsg:
    def __init__(self, type_, data=None):
        self.type = type_
        self._data = data

    def json(self):
        return self._data


class _FakeWS:
    """Async-iterable websocket that yields a fixed list of messages once."""

    def __init__(self, messages):
        self._messages = messages

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    def __aiter__(self):
        self._it = iter(self._messages)
        return self

    async def __anext__(self):
        try:
            return next(self._it)
        except StopIteration:
            raise StopAsyncIteration


def _ws_session(ws):
    """aiohttp.ClientSession() context manager whose ws_connect returns `ws`."""
    http = MagicMock()
    http.ws_connect = MagicMock(return_value=ws)
    session_cm = AsyncMock()
    session_cm.__aenter__ = AsyncMock(return_value=http)
    session_cm.__aexit__ = AsyncMock(return_value=False)
    return MagicMock(return_value=session_cm)


async def _run_listen(veil_settings, messages, **kw):
    """Drive one pass of listen_decisions; break the reconnect loop via sleep."""
    ws = _FakeWS(messages)
    with patch("aiohttp.ClientSession", _ws_session(ws)), patch(
        f"{_MOD}.asyncio.sleep", AsyncMock(side_effect=asyncio.CancelledError)
    ):
        with pytest.raises(asyncio.CancelledError):
            await veil.listen_decisions(**kw)


async def test_listen_decisions_no_url_is_noop(veil_settings):
    veil_settings.VEIL_URL = ""
    on_decision = AsyncMock()
    await veil.listen_decisions(on_decision)  # returns immediately, no raise
    on_decision.assert_not_awaited()


async def test_listen_decisions_routes_modqueue_and_chat(veil_settings):
    on_decision, on_connect, on_chat = AsyncMock(), AsyncMock(), AsyncMock()
    messages = [
        _WSMsg(
            aiohttp.WSMsgType.TEXT,
            {
                "type": "modqueue.decision",
                "data": {"message_id": "m1", "decision": "approve", "platform": "youtube"},
            },
        ),
        _WSMsg(
            aiohttp.WSMsgType.TEXT,
            {"type": "chat.send.request", "data": {"text": "hi", "targets": ["twitch"]}},
        ),
        _WSMsg(aiohttp.WSMsgType.CLOSED),
    ]
    await _run_listen(
        veil_settings,
        messages,
        on_decision=on_decision,
        on_connect=on_connect,
        on_chat_send=on_chat,
    )
    on_connect.assert_awaited_once()
    on_decision.assert_awaited_once_with("m1", "approve", "youtube")
    on_chat.assert_awaited_once_with("hi", ["twitch"])


async def test_listen_decisions_modqueue_defaults_platform_to_twitch(veil_settings):
    on_decision = AsyncMock()
    messages = [
        _WSMsg(aiohttp.WSMsgType.TEXT, {"type": "modqueue.decision", "data": {}}),
        _WSMsg(aiohttp.WSMsgType.CLOSED),
    ]
    await _run_listen(veil_settings, messages, on_decision=on_decision)
    on_decision.assert_awaited_once_with("", "", "twitch")


async def test_listen_decisions_ignores_chat_when_no_handler(veil_settings):
    on_decision = AsyncMock()
    messages = [
        _WSMsg(aiohttp.WSMsgType.TEXT, {"type": "chat.send.request", "data": {"text": "x"}}),
        _WSMsg(aiohttp.WSMsgType.CLOSED),
    ]
    # on_chat_send omitted → chat request must be silently dropped, no crash.
    await _run_listen(veil_settings, messages, on_decision=on_decision)
    on_decision.assert_not_awaited()
