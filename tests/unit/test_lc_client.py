# tests/unit/test_lc_client.py
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from couchd.core.clients.leetcode import LeetCodeClient


@pytest.fixture
def client():
    return LeetCodeClient()


def _make_aiohttp_mock(status: int, json_data: dict):
    mock_resp = AsyncMock()
    mock_resp.status = status
    mock_resp.json = AsyncMock(return_value=json_data)

    mock_post_cm = AsyncMock()
    mock_post_cm.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_post_cm.__aexit__ = AsyncMock(return_value=False)

    mock_http = AsyncMock()
    mock_http.post = MagicMock(return_value=mock_post_cm)

    mock_session_cm = AsyncMock()
    mock_session_cm.__aenter__ = AsyncMock(return_value=mock_http)
    mock_session_cm.__aexit__ = AsyncMock(return_value=False)

    return MagicMock(return_value=mock_session_cm)


async def test_fetch_recent_ac_returns_parsed_list(client):
    submissions = [
        {"id": "123", "titleSlug": "two-sum", "timestamp": "1700000000"},
        {"id": "456", "titleSlug": "add-two-numbers", "timestamp": "1700000001"},
    ]
    mock_session = _make_aiohttp_mock(200, {"data": {"recentAcSubmissionList": submissions}})

    with patch("aiohttp.ClientSession", mock_session):
        result = await client.fetch_recent_ac_submissions("testuser")

    assert result == submissions


async def test_fetch_recent_ac_http_error_returns_empty(client):
    mock_session = _make_aiohttp_mock(500, {})

    with patch("aiohttp.ClientSession", mock_session):
        result = await client.fetch_recent_ac_submissions("testuser")

    assert result == []


async def test_fetch_recent_ac_network_exception_returns_empty(client):
    with patch("aiohttp.ClientSession", side_effect=Exception("network error")):
        result = await client.fetch_recent_ac_submissions("testuser")

    assert result == []
