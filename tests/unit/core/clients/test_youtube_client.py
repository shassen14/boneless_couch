# tests/unit/core/clients/test_youtube_client.py
from unittest.mock import AsyncMock, MagicMock, patch

from couchd.core.clients.youtube import YouTubeRSSClient

_SAMPLE_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"
      xmlns:yt="http://www.youtube.com/xml/schemas/2015"
      xmlns:media="http://search.yahoo.com/mrss/">
  <entry>
    <yt:videoId>abc123</yt:videoId>
    <title>Test Video Title</title>
    <media:group>
      <media:thumbnail url="https://i.ytimg.com/vi/abc123/hqdefault.jpg"/>
    </media:group>
  </entry>
</feed>
"""

_EMPTY_FEED_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
</feed>
"""


def _make_aiohttp_mock(status: int, text: str):
    mock_resp = AsyncMock()
    mock_resp.status = status
    mock_resp.text = AsyncMock(return_value=text)

    mock_get_cm = AsyncMock()
    mock_get_cm.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_get_cm.__aexit__ = AsyncMock(return_value=False)

    mock_http = AsyncMock()
    mock_http.get = MagicMock(return_value=mock_get_cm)

    mock_session_cm = AsyncMock()
    mock_session_cm.__aenter__ = AsyncMock(return_value=mock_http)
    mock_session_cm.__aexit__ = AsyncMock(return_value=False)

    return MagicMock(return_value=mock_session_cm)


async def test_get_latest_video_returns_parsed_dict():
    client = YouTubeRSSClient()
    mock_session = _make_aiohttp_mock(200, _SAMPLE_XML)

    with patch("aiohttp.ClientSession", mock_session):
        result = await client.get_latest_video()

    assert result is not None
    assert result["video_id"] == "abc123"
    assert result["title"] == "Test Video Title"
    assert "abc123" in result["video_url"]
    assert "abc123" in result["thumbnail_url"]


async def test_get_latest_video_http_error_returns_none():
    client = YouTubeRSSClient()
    mock_session = _make_aiohttp_mock(404, "")

    with patch("aiohttp.ClientSession", mock_session):
        result = await client.get_latest_video()

    assert result is None


async def test_get_latest_video_network_exception_returns_none():
    client = YouTubeRSSClient()
    with patch("aiohttp.ClientSession", side_effect=Exception("network error")):
        result = await client.get_latest_video()

    assert result is None


async def test_get_latest_video_empty_feed_returns_none():
    client = YouTubeRSSClient()
    mock_session = _make_aiohttp_mock(200, _EMPTY_FEED_XML)

    with patch("aiohttp.ClientSession", mock_session):
        result = await client.get_latest_video()

    assert result is None


# ── 404 / 5xx branches ────────────────────────────────────────────────────────

async def test_get_latest_video_404_returns_none():
    mock_session = _make_aiohttp_mock(404, "")
    client = YouTubeRSSClient()
    with patch("aiohttp.ClientSession", mock_session):
        assert await client.get_latest_video() is None


async def test_get_latest_video_500_returns_none():
    # 5xx surfaces as ClientResponseError internally → swallowed, returns None.
    mock_session = _make_aiohttp_mock(503, "")
    client = YouTubeRSSClient()
    with patch("aiohttp.ClientSession", mock_session):
        assert await client.get_latest_video() is None


# ── is_livestream ─────────────────────────────────────────────────────────────

def _json_mock(status: int, json_data: dict):
    mock_resp = AsyncMock()
    mock_resp.status = status
    mock_resp.json = AsyncMock(return_value=json_data)
    cm = AsyncMock()
    cm.__aenter__ = AsyncMock(return_value=mock_resp)
    cm.__aexit__ = AsyncMock(return_value=False)
    http = AsyncMock()
    http.get = MagicMock(return_value=cm)
    session_cm = AsyncMock()
    session_cm.__aenter__ = AsyncMock(return_value=http)
    session_cm.__aexit__ = AsyncMock(return_value=False)
    return MagicMock(return_value=session_cm)


async def test_is_livestream_no_api_key_returns_none():
    client = YouTubeRSSClient()
    client.api_key = None
    assert await client.is_livestream("vid") is None


async def test_is_livestream_no_video_id_returns_none():
    client = YouTubeRSSClient()
    client.api_key = "KEY"
    assert await client.is_livestream("") is None


async def test_is_livestream_true_for_live():
    client = YouTubeRSSClient()
    client.api_key = "KEY"
    data = {"items": [{"snippet": {"liveBroadcastContent": "live"}}]}
    with patch("aiohttp.ClientSession", _json_mock(200, data)):
        assert await client.is_livestream("vid") is True


async def test_is_livestream_false_for_normal_upload():
    client = YouTubeRSSClient()
    client.api_key = "KEY"
    data = {"items": [{"snippet": {"liveBroadcastContent": "none"}}]}
    with patch("aiohttp.ClientSession", _json_mock(200, data)):
        assert await client.is_livestream("vid") is False


async def test_is_livestream_no_items_returns_none():
    client = YouTubeRSSClient()
    client.api_key = "KEY"
    with patch("aiohttp.ClientSession", _json_mock(200, {"items": []})):
        assert await client.is_livestream("vid") is None


async def test_is_livestream_http_error_returns_none():
    client = YouTubeRSSClient()
    client.api_key = "KEY"
    with patch("aiohttp.ClientSession", _json_mock(403, {})):
        assert await client.is_livestream("vid") is None


async def test_is_livestream_exception_returns_none():
    client = YouTubeRSSClient()
    client.api_key = "KEY"
    with patch("aiohttp.ClientSession", side_effect=Exception("boom")):
        assert await client.is_livestream("vid") is None
