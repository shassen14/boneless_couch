# tests/unit/core/clients/test_emotes_client.py
from unittest.mock import AsyncMock, MagicMock, patch

from couchd.core.clients.emotes import EmoteClient


# ── _parse_7tv ───────────────────────────────────────────────────────────────

def test_parse_7tv_prefers_2x_file():
    emotes = [
        {
            "name": "Pog",
            "data": {
                "host": {
                    "url": "//cdn.7tv.app/emote/abc",
                    "files": [
                        {"name": "1x.webp"},
                        {"name": "2x.webp"},
                        {"name": "4x.webp"},
                    ],
                }
            },
        }
    ]
    result = EmoteClient._parse_7tv(emotes)
    assert result == {"Pog": "https://cdn.7tv.app/emote/abc/2x.webp"}


def test_parse_7tv_falls_back_to_first_file():
    emotes = [
        {
            "name": "Kappa",
            "data": {"host": {"url": "//cdn/x", "files": [{"name": "1x.webp"}]}},
        }
    ]
    result = EmoteClient._parse_7tv(emotes)
    assert result == {"Kappa": "https://cdn/x/1x.webp"}


def test_parse_7tv_skips_missing_host_and_empty_files():
    emotes = [
        {"name": "NoData", "data": None},
        {"name": "NoHost", "data": {}},
        {"name": "NoFiles", "data": {"host": {"url": "//cdn/y", "files": []}}},
    ]
    assert EmoteClient._parse_7tv(emotes) == {}


# ── _parse_bttv ──────────────────────────────────────────────────────────────

def test_parse_bttv_builds_cdn_url():
    emotes = [{"code": "FeelsGood", "id": "123", "imageType": "gif"}]
    result = EmoteClient._parse_bttv(emotes)
    assert result == {"FeelsGood": "https://cdn.betterttv.net/emote/123/2x.gif"}


def test_parse_bttv_defaults_image_type_to_png():
    emotes = [{"code": "Sad", "id": "9"}]
    result = EmoteClient._parse_bttv(emotes)
    assert result["Sad"].endswith("/2x.png")


def test_parse_bttv_skips_incomplete_entries():
    emotes = [{"code": "OnlyCode"}, {"id": "onlyid"}, {}]
    assert EmoteClient._parse_bttv(emotes) == {}


# ── _parse_ffz_set ───────────────────────────────────────────────────────────

def test_parse_ffz_set_prefers_2x_and_prefixes_scheme():
    set_data = {"emoticons": [{"name": "ZULUL", "urls": {"1": "//ffz/1", "2": "//ffz/2"}}]}
    result = EmoteClient._parse_ffz_set(set_data)
    assert result == {"ZULUL": "https://ffz/2"}


def test_parse_ffz_set_falls_back_to_1x():
    set_data = {"emoticons": [{"name": "X", "urls": {"1": "//ffz/1"}}]}
    result = EmoteClient._parse_ffz_set(set_data)
    assert result == {"X": "https://ffz/1"}


def test_parse_ffz_set_keeps_existing_scheme():
    set_data = {"emoticons": [{"name": "X", "urls": {"2": "https://already/2"}}]}
    result = EmoteClient._parse_ffz_set(set_data)
    assert result == {"X": "https://already/2"}


def test_parse_ffz_set_skips_missing_name_or_urls():
    set_data = {"emoticons": [{"urls": {"1": "//x"}}, {"name": "NoUrls", "urls": {}}]}
    assert EmoteClient._parse_ffz_set(set_data) == {}


# ── fetch_all aggregation ────────────────────────────────────────────────────

async def test_fetch_all_merges_results_and_ignores_exceptions():
    client = EmoteClient()
    with patch.object(client, "_fetch_7tv_global", AsyncMock(return_value={"A": "1"})), \
         patch.object(client, "_fetch_7tv_channel", AsyncMock(return_value={"B": "2"})), \
         patch.object(client, "_fetch_bttv_global", AsyncMock(side_effect=Exception("boom"))), \
         patch.object(client, "_fetch_bttv_channel", AsyncMock(return_value={"C": "3"})), \
         patch.object(client, "_fetch_ffz_global", AsyncMock(return_value={})), \
         patch.object(client, "_fetch_ffz_channel", AsyncMock(return_value={"D": "4"})):
        result = await client.fetch_all("chan", "123")
    assert result == {"A": "1", "B": "2", "C": "3", "D": "4"}


async def test_fetch_channel_endpoints_skip_when_no_id():
    client = EmoteClient()
    # No network patching: empty channel_id must short-circuit before any request.
    assert await client._fetch_7tv_channel("") == {}
    assert await client._fetch_bttv_channel("") == {}
    assert await client._fetch_ffz_channel("") == {}


def _make_aiohttp_mock(status: int, json_data):
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


async def test_fetch_7tv_global_non_200_returns_empty():
    client = EmoteClient()
    with patch("aiohttp.ClientSession", _make_aiohttp_mock(503, {})):
        assert await client._fetch_7tv_global() == {}


async def test_fetch_bttv_global_handles_non_list_payload():
    client = EmoteClient()
    with patch("aiohttp.ClientSession", _make_aiohttp_mock(200, {"unexpected": "object"})):
        assert await client._fetch_bttv_global() == {}


# ── fetch_* success paths ─────────────────────────────────────────────────────


async def test_fetch_7tv_global_parses_payload():
    client = EmoteClient()
    payload = {"emotes": [{"name": "Pog", "data": {"host": {"url": "//cdn/x", "files": [{"name": "2x.webp"}]}}}]}
    with patch("aiohttp.ClientSession", _make_aiohttp_mock(200, payload)):
        assert await client._fetch_7tv_global() == {"Pog": "https://cdn/x/2x.webp"}


async def test_fetch_7tv_channel_reads_nested_emote_set():
    client = EmoteClient()
    payload = {"emote_set": {"emotes": [{"name": "Kappa", "data": {"host": {"url": "//cdn/k", "files": [{"name": "2x.webp"}]}}}]}}
    with patch("aiohttp.ClientSession", _make_aiohttp_mock(200, payload)):
        assert await client._fetch_7tv_channel("123") == {"Kappa": "https://cdn/k/2x.webp"}


async def test_fetch_bttv_channel_merges_channel_and_shared():
    client = EmoteClient()
    payload = {
        "channelEmotes": [{"code": "A", "id": "1", "imageType": "png"}],
        "sharedEmotes": [{"code": "B", "id": "2", "imageType": "gif"}],
    }
    with patch("aiohttp.ClientSession", _make_aiohttp_mock(200, payload)):
        result = await client._fetch_bttv_channel("123")
    assert result == {
        "A": "https://cdn.betterttv.net/emote/1/2x.png",
        "B": "https://cdn.betterttv.net/emote/2/2x.gif",
    }


async def test_fetch_ffz_global_walks_default_sets():
    client = EmoteClient()
    payload = {
        "default_sets": [42],
        "sets": {"42": {"emoticons": [{"name": "Z", "urls": {"2": "//ffz/2"}}]}},
    }
    with patch("aiohttp.ClientSession", _make_aiohttp_mock(200, payload)):
        assert await client._fetch_ffz_global() == {"Z": "https://ffz/2"}


async def test_fetch_ffz_channel_walks_all_sets():
    client = EmoteClient()
    payload = {"sets": {"99": {"emoticons": [{"name": "Y", "urls": {"1": "//ffz/1"}}]}}}
    with patch("aiohttp.ClientSession", _make_aiohttp_mock(200, payload)):
        assert await client._fetch_ffz_channel("chan") == {"Y": "https://ffz/1"}


async def test_fetch_ffz_channel_non_200_returns_empty():
    client = EmoteClient()
    with patch("aiohttp.ClientSession", _make_aiohttp_mock(404, {})):
        assert await client._fetch_ffz_channel("chan") == {}
