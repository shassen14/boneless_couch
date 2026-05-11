# couchd/core/clients/codeforces.py
import logging
import re

import aiohttp

log = logging.getLogger(__name__)

_API_BASE = "https://codeforces.com/api"
_CF_BASE = "https://codeforces.com"

# Matches both /contest/{id}/problem/{index} and /problemset/problem/{id}/{index}
_PROBLEM_URL_RE = re.compile(
    r"codeforces\.com/(?:contest/(\d+)/problem|problemset/problem/(\d+))/([A-Za-z]\d*)"
)


def parse_problem_url(url: str) -> tuple[int, str] | None:
    m = _PROBLEM_URL_RE.search(url)
    if not m:
        return None
    contest_id = int(m.group(1) or m.group(2))
    index = m.group(3).upper()
    return contest_id, index


def problem_url(contest_id: int, index: str) -> str:
    return f"{_CF_BASE}/contest/{contest_id}/problem/{index}"


async def fetch_problem(contest_id: int, index: str) -> dict | None:
    """Return {title, rating, tags} for the given CF problem, or None on failure."""
    url = f"{_API_BASE}/contest.standings?contestId={contest_id}&from=1&count=1"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                data = await resp.json(content_type=None)
    except Exception:
        log.error("Failed to fetch CF problem %d%s", contest_id, index, exc_info=True)
        return None

    if data.get("status") != "OK":
        log.warning("CF API error for contest %d: %s", contest_id, data.get("comment"))
        return None

    problems = data.get("result", {}).get("problems", [])
    for p in problems:
        if p.get("index", "").upper() == index.upper():
            return {
                "title": p.get("name", "Unknown"),
                "rating": p.get("rating"),
                "tags": p.get("tags", []),
            }

    log.warning("Problem %d%s not found in standings response.", contest_id, index)
    return None


async def fetch_recent_ac_submissions(handle: str, count: int = 10) -> list[dict]:
    """Return recent accepted submissions for the given CF handle."""
    url = f"{_API_BASE}/user.status?handle={handle}&from=1&count={count}"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                data = await resp.json(content_type=None)
    except Exception:
        log.error("Failed to fetch CF submissions for %s", handle, exc_info=True)
        return []

    if data.get("status") != "OK":
        return []

    results = []
    for sub in data.get("result", []):
        if sub.get("verdict") != "OK":
            continue
        p = sub.get("problem", {})
        contest_id = p.get("contestId")
        index = p.get("index", "")
        if not contest_id or not index:
            continue
        results.append({
            "submission_id": sub.get("id"),
            "contest_id": contest_id,
            "index": index.upper(),
            "title": p.get("name", "Unknown"),
            "rating": p.get("rating"),
            "tags": p.get("tags", []),
        })
    return results
