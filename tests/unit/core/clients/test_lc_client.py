# tests/unit/core/clients/test_lc_client.py
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from couchd.core.clients.leetcode import LeetCodeClient


@pytest.fixture
def client():
    return LeetCodeClient()


def _make_aiohttp_mock(status: int, json_data: dict | None = None, text_data: str | None = None):
    mock_resp = AsyncMock()
    mock_resp.status = status
    mock_resp.json = AsyncMock(return_value=json_data)
    mock_resp.text = AsyncMock(return_value=text_data)

    mock_req_cm = AsyncMock()
    mock_req_cm.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_req_cm.__aexit__ = AsyncMock(return_value=False)

    mock_http = AsyncMock()
    mock_http.post = MagicMock(return_value=mock_req_cm)
    mock_http.get = MagicMock(return_value=mock_req_cm)

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


# ── fetch_problem ─────────────────────────────────────────────────────────────

async def test_fetch_problem_parses_metadata(client):
    question = {
        "questionFrontendId": "1",
        "title": "Two Sum",
        "difficulty": "Easy",
        "topicTags": [{"name": "Array"}, {"name": "Hash Table"}],
    }
    mock_session = _make_aiohttp_mock(200, {"data": {"question": question}})

    with patch("aiohttp.ClientSession", mock_session):
        result = await client.fetch_problem("two-sum")

    assert result == {
        "id": 1,
        "title": "Two Sum",
        "difficulty": "Easy",
        "tags": ["Array", "Hash Table"],
    }


async def test_fetch_problem_missing_topic_tags_defaults_empty(client):
    question = {"questionFrontendId": "42", "title": "X", "difficulty": "Hard"}
    mock_session = _make_aiohttp_mock(200, {"data": {"question": question}})

    with patch("aiohttp.ClientSession", mock_session):
        result = await client.fetch_problem("x")

    assert result["tags"] == []


async def test_fetch_problem_no_question_returns_none(client):
    mock_session = _make_aiohttp_mock(200, {"data": {"question": None}})

    with patch("aiohttp.ClientSession", mock_session):
        result = await client.fetch_problem("missing")

    assert result is None


async def test_fetch_problem_http_error_returns_none(client):
    mock_session = _make_aiohttp_mock(403, {})

    with patch("aiohttp.ClientSession", mock_session):
        result = await client.fetch_problem("two-sum")

    assert result is None


async def test_fetch_problem_network_exception_returns_none(client):
    with patch("aiohttp.ClientSession", side_effect=Exception("boom")):
        result = await client.fetch_problem("two-sum")

    assert result is None


# ── load_ratings / get_rating ─────────────────────────────────────────────────

async def test_load_ratings_parses_tab_separated_lines(client):
    text = (
        "Rating\tID\tTitle\n"      # header-like row: ID col not an int → skipped
        "1500.5\t1\tTwo Sum\n"
        "2000.0\t42\tTrapping Rain\n"
        "\n"                         # blank line skipped
        "garbage line\n"            # too few columns / non-numeric → skipped
    )
    mock_session = _make_aiohttp_mock(200, text_data=text)

    with patch("aiohttp.ClientSession", mock_session):
        await client.load_ratings()

    assert client.get_rating(1) == 1500.5
    assert client.get_rating(42) == 2000.0
    assert client.get_rating(999) is None


async def test_load_ratings_http_error_leaves_cache_empty(client):
    mock_session = _make_aiohttp_mock(500, text_data="")

    with patch("aiohttp.ClientSession", mock_session):
        await client.load_ratings()

    assert client.get_rating(1) is None


async def test_load_ratings_network_exception_is_swallowed(client):
    with patch("aiohttp.ClientSession", side_effect=Exception("boom")):
        await client.load_ratings()

    assert client.get_rating(1) is None
