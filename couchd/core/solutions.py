# couchd/core/solutions.py
import logging
from sqlalchemy import select

from couchd.core.db import get_session
from couchd.core.models import CFProblemAttempt, SolutionPost, StreamEvent, StreamSession
from couchd.core.constants import Platform
from couchd.core.clients import codeforces as cf_client
from couchd.core.utils import get_active_session, compute_vod_timestamp

log = logging.getLogger(__name__)


async def upsert_solution(
    problem_slug: str, platform: str, username: str, url: str, vod_ts: str | None
) -> bool:
    """Record one user's solution for a problem. Returns False when the URL is unchanged."""
    async with get_session() as db:
        sol = (
            await db.execute(
                select(SolutionPost).where(
                    SolutionPost.problem_slug == problem_slug,
                    SolutionPost.platform == platform,
                    SolutionPost.username == username,
                )
            )
        ).scalar_one_or_none()
        if sol and sol.url == url:
            return False
        if sol:
            sol.url = url
            sol.vod_timestamp = vod_ts
        else:
            db.add(
                SolutionPost(
                    problem_slug=problem_slug,
                    platform=platform,
                    username=username,
                    url=url,
                    vod_timestamp=vod_ts,
                )
            )
        await db.commit()
    return True


async def current_cf_attempt(session: StreamSession) -> CFProblemAttempt | None:
    async with get_session() as db:
        return (
            await db.execute(
                select(CFProblemAttempt)
                .join(StreamEvent)
                .where(StreamEvent.session_id == session.id)
                .order_by(StreamEvent.timestamp.desc())
                .limit(1)
            )
        ).scalar_one_or_none()


async def record_cf_solution(text: str, platform: Platform, username: str) -> None:
    """Attach a pasted CF submission link to the problem currently on stream."""
    ref = cf_client.parse_submission_url(text)
    if not ref:
        return

    # !cf logs against the Twitch session on every platform, so that's where to look.
    active_session = await get_active_session()
    attempt = await current_cf_attempt(active_session) if active_session else None
    # Submission links only name the contest, so a link from another contest can't be
    # for the problem on stream.
    if not attempt or attempt.contest_id != ref.contest_id:
        return

    vod_ts = compute_vod_timestamp(active_session.start_time)
    if await upsert_solution(attempt.problem_id, platform.value, username, ref.url, vod_ts):
        log.info("Logged CF solution from %s for %s", username, attempt.problem_id)
