# couchd/core/clients/codeforces.py
import logging
import re
import time
from typing import NamedTuple

import aiohttp

from couchd.core.constants import CFConfig

log = logging.getLogger(__name__)

# An index is a letter with an optional division suffix (A, C2), except on acmsguru
# where problems are numbered instead (101).
_INDEX = r"[A-Za-z]\d*|\d+"

# /contest/{id}/problem/{index} and /gym/{id}/problem/{index}, plus every wrapper that
# embeds that same tail behind a longer path — edu course lessons, mashups, ACM groups.
_CONTEST_RE = re.compile(
    rf"codeforces\.com/(?P<prefix>\S*?/)?(?P<kind>contest|gym)/(?P<contest>\d+)/problem/(?P<index>{_INDEX})"
)
# /problemset/problem/{id}/{index} — the archive view of a regular contest problem.
_PROBLEMSET_RE = re.compile(
    rf"codeforces\.com/problemset/problem/(?P<contest>\d+)/(?P<index>{_INDEX})"
)
# /problemsets/acmsguru/problem/99999/{number} — the imported acm.sgu.ru archive.
_ACMSGURU_RE = re.compile(
    r"codeforces\.com/problemsets/acmsguru/problem/(?P<contest>\d+)/(?P<index>\d+)"
)


class CFProblemRef(NamedTuple):
    contest_id: int
    index: str
    url: str


def problem_url(contest_id: int, index: str) -> str:
    return f"{CFConfig.BASE_URL}/contest/{contest_id}/problem/{index}"


def parse_problem_url(url: str) -> CFProblemRef | None:
    """Resolve any Codeforces problem link to (contest_id, index, canonical url)."""
    match = _CONTEST_RE.search(url)
    if match:
        contest_id = int(match.group("contest"))
        index = match.group("index").upper()
        if match.group("prefix"):
            # Wrapped problems (edu, mashups) are only reachable through the pasted
            # path, so keep it verbatim rather than inventing a /contest/ link.
            return CFProblemRef(contest_id, index, _matched_url(url, match))
        if match.group("kind") == "gym":
            return CFProblemRef(
                contest_id, index, f"{CFConfig.BASE_URL}/gym/{contest_id}/problem/{index}"
            )
        return CFProblemRef(contest_id, index, problem_url(contest_id, index))

    match = _PROBLEMSET_RE.search(url)
    if match:
        contest_id = int(match.group("contest"))
        index = match.group("index").upper()
        return CFProblemRef(contest_id, index, problem_url(contest_id, index))

    match = _ACMSGURU_RE.search(url)
    if match:
        return CFProblemRef(
            int(match.group("contest")), match.group("index"), _matched_url(url, match)
        )

    return None


def _matched_url(url: str, match: re.Match) -> str:
    """The matched span only, so trailing text or query params are dropped."""
    return f"https://{url[match.start():match.end()]}"


async def _get_json(url: str, timeout: int) -> dict | None:
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=timeout)) as resp:
                data = await resp.json(content_type=None)
    except Exception:
        log.error("Codeforces request failed: %s", url, exc_info=True)
        return None

    if data.get("status") != "OK":
        log.warning("CF API error for %s: %s", url, data.get("comment"))
        return None
    return data


def _problem_info(problem: dict) -> dict:
    return {
        "title": problem.get("name", "Unknown"),
        "rating": problem.get("rating"),
        "tags": problem.get("tags", []),
    }


_problemset: dict[tuple[int, str], dict] = {}
_problemset_fetched_at: float = 0.0


async def _refresh_problemset() -> None:
    """Cache the whole non-gym problem archive; it is one cheap call for every problem."""
    global _problemset_fetched_at
    fresh = time.monotonic() - _problemset_fetched_at < CFConfig.PROBLEMSET_CACHE_TTL_SECONDS
    if _problemset and fresh:
        return

    data = await _get_json(
        f"{CFConfig.API_BASE}/problemset.problems", CFConfig.BULK_TIMEOUT_SECONDS
    )
    if not data:
        return

    _problemset.clear()
    for p in data.get("result", {}).get("problems", []):
        contest_id, index = p.get("contestId"), p.get("index")
        if contest_id and index:
            _problemset[(contest_id, index.upper())] = _problem_info(p)
    _problemset_fetched_at = time.monotonic()


async def fetch_problem(contest_id: int, index: str) -> dict | None:
    """Return {title, rating, tags} for the given CF problem, or None on failure."""
    index = index.upper()
    await _refresh_problemset()
    cached = _problemset.get((contest_id, index))
    if cached:
        return cached

    # Problems too new for the archive: contest.standings still has them, but the API
    # rejects it for non-admins unless the request carries no extra query parameters.
    data = await _get_json(
        f"{CFConfig.API_BASE}/contest.standings?contestId={contest_id}",
        CFConfig.BULK_TIMEOUT_SECONDS,
    )
    if not data:
        return None

    for p in data.get("result", {}).get("problems", []):
        if p.get("index", "").upper() == index:
            return _problem_info(p)

    log.warning("Problem %d%s not found in standings response.", contest_id, index)
    return None


async def resolve_problem(url: str, title: str | None = None) -> dict | None:
    """Parse any CF problem link and attach its metadata. None only if the URL is not one."""
    ref = parse_problem_url(url)
    if not ref:
        return None

    info = await fetch_problem(ref.contest_id, ref.index)
    # Gym, edu-course and mashup problems are not served by the public API, so they
    # carry no rating or tags and fall back to the title the streamer typed.
    info = dict(info) if info else {
        "title": f"Contest {ref.contest_id} · Problem {ref.index}",
        "rating": None,
        "tags": [],
    }
    if title:
        info["title"] = title
    return {"contest_id": ref.contest_id, "index": ref.index, "url": ref.url, **info}


def describe(problem_id: str, title: str, rating: int | None) -> str:
    """One-line chat description shared by every platform's !cf output."""
    rating_str = f" · {rating}" if rating else ""
    return f"{problem_id} · {title}{rating_str}"


async def fetch_recent_ac_submissions(handle: str, count: int = 10) -> list[dict]:
    """Return recent accepted submissions for the given CF handle."""
    url = f"{CFConfig.API_BASE}/user.status?handle={handle}&from=1&count={count}"
    data = await _get_json(url, CFConfig.REQUEST_TIMEOUT_SECONDS)
    if not data:
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
