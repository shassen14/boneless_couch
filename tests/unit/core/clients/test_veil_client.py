# tests/unit/core/clients/test_veil_client.py
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
