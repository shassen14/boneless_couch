# tests/unit/core/clients/test_codeforces_client.py
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from couchd.core.clients import codeforces


def _make_aiohttp_mock(json_data: dict):
    mock_resp = AsyncMock()
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


# ── parse_problem_url ────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "url,expected",
    [
        ("https://codeforces.com/contest/1234/problem/A", (1234, "A")),
        ("https://codeforces.com/contest/1234/problem/a", (1234, "A")),
        ("https://codeforces.com/problemset/problem/1234/B2", (1234, "B2")),
        ("http://codeforces.com/contest/9/problem/C", (9, "C")),
        ("codeforces.com/contest/1/problem/F1", (1, "F1")),
    ],
)
def test_parse_problem_url_valid(url, expected):
    assert codeforces.parse_problem_url(url) == expected


@pytest.mark.parametrize(
    "url",
    [
        "https://leetcode.com/problems/two-sum/",
        "https://codeforces.com/profile/tourist",
        "not a url at all",
        "",
        "https://codeforces.com/contest/abc/problem/A",  # non-numeric contest
    ],
)
def test_parse_problem_url_invalid(url):
    assert codeforces.parse_problem_url(url) is None


def test_problem_url_round_trips_with_parse():
    url = codeforces.problem_url(1700, "D")
    assert codeforces.parse_problem_url(url) == (1700, "D")


# ── fetch_problem ────────────────────────────────────────────────────────────

async def test_fetch_problem_returns_matching_problem():
    data = {
        "status": "OK",
        "result": {
            "problems": [
                {"index": "A", "name": "Watermelon", "rating": 800, "tags": ["math"]},
                {"index": "B", "name": "Other", "rating": 1000, "tags": []},
            ]
        },
    }
    with patch("aiohttp.ClientSession", _make_aiohttp_mock(data)):
        result = await codeforces.fetch_problem(4, "A")
    assert result == {"title": "Watermelon", "rating": 800, "tags": ["math"]}


async def test_fetch_problem_index_case_insensitive():
    data = {"status": "OK", "result": {"problems": [{"index": "C", "name": "X"}]}}
    with patch("aiohttp.ClientSession", _make_aiohttp_mock(data)):
        result = await codeforces.fetch_problem(4, "c")
    assert result["title"] == "X"
    assert result["rating"] is None
    assert result["tags"] == []


async def test_fetch_problem_not_found_returns_none():
    data = {"status": "OK", "result": {"problems": [{"index": "A", "name": "X"}]}}
    with patch("aiohttp.ClientSession", _make_aiohttp_mock(data)):
        result = await codeforces.fetch_problem(4, "Z")
    assert result is None


async def test_fetch_problem_api_failed_status_returns_none():
    data = {"status": "FAILED", "comment": "contestId: out of range"}
    with patch("aiohttp.ClientSession", _make_aiohttp_mock(data)):
        result = await codeforces.fetch_problem(99999999, "A")
    assert result is None


async def test_fetch_problem_network_exception_returns_none():
    with patch("aiohttp.ClientSession", side_effect=Exception("boom")):
        result = await codeforces.fetch_problem(4, "A")
    assert result is None


# ── fetch_recent_ac_submissions ──────────────────────────────────────────────

async def test_fetch_recent_ac_filters_non_ok_verdicts():
    data = {
        "status": "OK",
        "result": [
            {
                "id": 1,
                "verdict": "OK",
                "problem": {"contestId": 100, "index": "a", "name": "P1", "rating": 900, "tags": ["dp"]},
            },
            {
                "id": 2,
                "verdict": "WRONG_ANSWER",
                "problem": {"contestId": 100, "index": "B", "name": "P2"},
            },
        ],
    }
    with patch("aiohttp.ClientSession", _make_aiohttp_mock(data)):
        results = await codeforces.fetch_recent_ac_submissions("tourist")
    assert len(results) == 1
    assert results[0] == {
        "submission_id": 1,
        "contest_id": 100,
        "index": "A",
        "title": "P1",
        "rating": 900,
        "tags": ["dp"],
    }


async def test_fetch_recent_ac_skips_submissions_missing_contest_or_index():
    data = {
        "status": "OK",
        "result": [
            {"id": 1, "verdict": "OK", "problem": {"index": "A", "name": "no contest"}},
            {"id": 2, "verdict": "OK", "problem": {"contestId": 5, "name": "no index"}},
        ],
    }
    with patch("aiohttp.ClientSession", _make_aiohttp_mock(data)):
        results = await codeforces.fetch_recent_ac_submissions("tourist")
    assert results == []


async def test_fetch_recent_ac_api_failed_returns_empty():
    data = {"status": "FAILED", "comment": "handle not found"}
    with patch("aiohttp.ClientSession", _make_aiohttp_mock(data)):
        results = await codeforces.fetch_recent_ac_submissions("ghost")
    assert results == []


async def test_fetch_recent_ac_network_exception_returns_empty():
    with patch("aiohttp.ClientSession", side_effect=Exception("boom")):
        results = await codeforces.fetch_recent_ac_submissions("tourist")
    assert results == []
