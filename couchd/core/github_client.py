# couchd/core/github_client.py
import logging
import aiohttp

from couchd.core.constants import GitHubConfig

log = logging.getLogger(__name__)


class GitHubClient:
    """Fetches GitHub repository metadata."""

    async def fetch_repo(self, owner: str, repo: str) -> str | None:
        """Return the repository description, or None on failure."""
        try:
            async with aiohttp.ClientSession() as http:
                url = f"{GitHubConfig.API_BASE}/{owner}/{repo}"
                async with http.get(
                    url, headers={"Accept": "application/vnd.github+json"}
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return data.get("description") or None
                    log.warning(
                        "GitHub API returned HTTP %s for %s/%s", resp.status, owner, repo
                    )
                    return None
        except Exception:
            log.warning("Exception fetching GitHub repo info", exc_info=True)
            return None
