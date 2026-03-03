# tests/unit/core/clients/test_github_client.py
from unittest.mock import AsyncMock, MagicMock, patch

from couchd.core.clients.github import GitHubClient


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


async def test_fetch_repo_returns_description():
    client = GitHubClient()
    mock_session = _make_aiohttp_mock(200, {"description": "A cool repo"})

    with patch("aiohttp.ClientSession", mock_session):
        result = await client.fetch_repo("owner", "repo")

    assert result == "A cool repo"


async def test_fetch_repo_null_description_returns_none():
    client = GitHubClient()
    mock_session = _make_aiohttp_mock(200, {"description": None})

    with patch("aiohttp.ClientSession", mock_session):
        result = await client.fetch_repo("owner", "repo")

    assert result is None


async def test_fetch_repo_non_200_returns_none():
    client = GitHubClient()
    mock_session = _make_aiohttp_mock(404, {})

    with patch("aiohttp.ClientSession", mock_session):
        result = await client.fetch_repo("owner", "repo")

    assert result is None


async def test_fetch_repo_network_exception_returns_none():
    client = GitHubClient()
    with patch("aiohttp.ClientSession", side_effect=Exception("network error")):
        result = await client.fetch_repo("owner", "repo")

    assert result is None
