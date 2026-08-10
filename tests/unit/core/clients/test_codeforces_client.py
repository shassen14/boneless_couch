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


@pytest.fixture(autouse=True)
def _clear_problemset_cache():
    """The archive cache is module-level; keep it from leaking between tests."""
    codeforces._problemset.clear()
    codeforces._problemset_fetched_at = 0.0
    yield
    codeforces._problemset.clear()
    codeforces._problemset_fetched_at = 0.0


# ── parse_problem_url ────────────────────────────────────────────────────────

CF = "https://codeforces.com"
EDU = f"{CF}/edu/course/2/lesson/7/1/practice/contest/289390/problem/C"
GYM = f"{CF}/gym/104555/problem/A"
ACMSGURU = f"{CF}/problemsets/acmsguru/problem/99999/101"


@pytest.mark.parametrize(
    "url,expected",
    [
        (f"{CF}/contest/1234/problem/A", (1234, "A", f"{CF}/contest/1234/problem/A")),
        (f"{CF}/contest/1234/problem/a", (1234, "A", f"{CF}/contest/1234/problem/A")),
        # problemset links normalise to the canonical /contest/ form
        (f"{CF}/problemset/problem/1234/B2", (1234, "B2", f"{CF}/contest/1234/problem/B2")),
        ("http://codeforces.com/contest/9/problem/C", (9, "C", f"{CF}/contest/9/problem/C")),
        ("codeforces.com/contest/1/problem/F1", (1, "F1", f"{CF}/contest/1/problem/F1")),
        # query params and trailing text are dropped
        (f"{CF}/contest/1234/problem/A?locale=en", (1234, "A", f"{CF}/contest/1234/problem/A")),
        # wrapped and non-contest archives keep the pasted path — it is the only one that resolves
        (EDU, (289390, "C", EDU)),
        (GYM, (104555, "A", GYM)),
        (ACMSGURU, (99999, "101", ACMSGURU)),
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
    assert codeforces.parse_problem_url(url) == (1700, "D", url)


# ── resolve_problem ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_resolve_problem_attaches_api_metadata():
    info = {"title": "P", "rating": 900, "tags": ["dp"]}
    with patch.object(codeforces, "fetch_problem", AsyncMock(return_value=info)):
        result = await codeforces.resolve_problem(f"{CF}/contest/1700/problem/D")
    assert result == {
        "contest_id": 1700,
        "index": "D",
        "url": f"{CF}/contest/1700/problem/D",
        **info,
    }


@pytest.mark.asyncio
async def test_resolve_problem_falls_back_when_api_has_no_entry():
    """Gym/edu problems are absent from the API but must still be loggable."""
    with patch.object(codeforces, "fetch_problem", AsyncMock(return_value=None)):
        result = await codeforces.resolve_problem(EDU)
    assert result["title"] == "Contest 289390 · Problem C"
    assert result["url"] == EDU
    assert result["rating"] is None
    assert result["tags"] == []


@pytest.mark.asyncio
async def test_resolve_problem_title_override_wins():
    with patch.object(codeforces, "fetch_problem", AsyncMock(return_value=None)):
        result = await codeforces.resolve_problem(EDU, "Number of Inversions")
    assert result["title"] == "Number of Inversions"


@pytest.mark.asyncio
async def test_resolve_problem_override_does_not_mutate_cached_metadata():
    info = {"title": "Real Title", "rating": 800, "tags": []}
    with patch.object(codeforces, "fetch_problem", AsyncMock(return_value=info)):
        await codeforces.resolve_problem(f"{CF}/contest/1/problem/A", "Override")
    assert info["title"] == "Real Title"


@pytest.mark.asyncio
async def test_resolve_problem_returns_none_for_non_cf_url():
    assert await codeforces.resolve_problem("https://leetcode.com/problems/two-sum/") is None


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


async def test_fetch_problem_serves_from_problemset_archive():
    """The archive answers without falling through to a standings request."""
    data = {
        "status": "OK",
        "result": {
            "problems": [
                {"contestId": 1915, "index": "A", "name": "Odd One Out",
                 "rating": 800, "tags": ["math"]},
            ]
        },
    }
    session = _make_aiohttp_mock(data)
    with patch("aiohttp.ClientSession", session):
        assert await codeforces.fetch_problem(1915, "A") == {
            "title": "Odd One Out", "rating": 800, "tags": ["math"],
        }
        # cached: a second lookup issues no further HTTP call
        assert (await codeforces.fetch_problem(1915, "A"))["title"] == "Odd One Out"
    assert session.call_count == 1


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
