# couchd/core/clients/leetcode.py
import logging
import aiohttp

from couchd.core.constants import LeetCodeConfig, ZerotracConfig

log = logging.getLogger(__name__)

_LC_GRAPHQL_QUERY = """
query questionData($titleSlug: String!) {
  question(titleSlug: $titleSlug) {
    questionId
    title
    difficulty
    topicTags {
      name
    }
  }
}
"""

_LC_RECENT_AC_QUERY = """
query recentAcSubmissions($username: String!, $limit: Int!) {
  recentAcSubmissionList(username: $username, limit: $limit) {
    id
    titleSlug
    timestamp
  }
}
"""


class LeetCodeClient:
    """Fetches LeetCode problem metadata and zerotrac difficulty ratings."""

    def __init__(self):
        self._ratings: dict[int, float] = {}

    async def load_ratings(self) -> None:
        """Download and parse the zerotrac ratings file into _ratings cache."""
        try:
            async with aiohttp.ClientSession() as http:
                async with http.get(ZerotracConfig.RATINGS_URL) as resp:
                    if resp.status != 200:
                        log.warning(
                            "Failed to fetch zerotrac ratings (HTTP %s). "
                            "Ratings will be unavailable.",
                            resp.status,
                        )
                        return
                    text = await resp.text()

            count = 0
            for line in text.splitlines():
                line = line.strip()
                if not line:
                    continue
                parts = line.split("\t")
                if len(parts) < 2:
                    continue
                try:
                    # zerotrac format: Rating\tID\tTitle\t...
                    rating = float(parts[0])
                    problem_id = int(parts[1])
                    self._ratings[problem_id] = rating
                    count += 1
                except (ValueError, IndexError):
                    # Skip header row and any malformed lines
                    continue

            log.info("Loaded %d zerotrac ratings.", count)
        except Exception:
            log.warning(
                "Exception loading zerotrac ratings. Ratings will be unavailable.",
                exc_info=True,
            )

    async def fetch_problem(self, slug: str) -> dict | None:
        """
        Fetch problem metadata from LeetCode GraphQL API.
        Returns {id: int, title: str, difficulty: str, tags: list[str]} or None on failure.
        """
        payload = {
            "query": _LC_GRAPHQL_QUERY,
            "variables": {"titleSlug": slug},
        }
        try:
            async with aiohttp.ClientSession() as http:
                async with http.post(
                    LeetCodeConfig.GRAPHQL_URL,
                    json=payload,
                    headers={"Content-Type": "application/json"},
                ) as resp:
                    if resp.status != 200:
                        log.warning(
                            "LeetCode GraphQL returned HTTP %s for slug '%s'.",
                            resp.status,
                            slug,
                        )
                        return None
                    data = await resp.json()

            question = data.get("data", {}).get("question")
            if not question:
                log.warning("LeetCode GraphQL: no question found for slug '%s'.", slug)
                return None

            return {
                "id": int(question["questionId"]),
                "title": question["title"],
                "difficulty": question["difficulty"],
                "tags": [t["name"] for t in question.get("topicTags", [])],
            }
        except Exception:
            log.warning(
                "Exception fetching LeetCode problem '%s'.", slug, exc_info=True
            )
            return None

    def get_rating(self, problem_id: int) -> float | None:
        """Return the zerotrac rating for a problem ID, or None if not in cache."""
        return self._ratings.get(problem_id)

    async def fetch_recent_ac_submissions(self, username: str, limit: int = 10) -> list[dict]:
        """
        Return recent accepted submissions for a LeetCode user.
        Each entry: {id: str, titleSlug: str, timestamp: str}
        """
        payload = {
            "query": _LC_RECENT_AC_QUERY,
            "variables": {"username": username, "limit": limit},
        }
        try:
            async with aiohttp.ClientSession() as http:
                async with http.post(
                    LeetCodeConfig.GRAPHQL_URL,
                    json=payload,
                    headers={"Content-Type": "application/json"},
                ) as resp:
                    if resp.status != 200:
                        log.warning("LeetCode GraphQL returned HTTP %s for recent AC.", resp.status)
                        return []
                    data = await resp.json()
            return data.get("data", {}).get("recentAcSubmissionList", []) or []
        except Exception:
            log.warning("Exception fetching recent AC submissions for '%s'.", username, exc_info=True)
            return []
