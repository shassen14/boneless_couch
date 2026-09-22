"""Create the Discord forum threads for Codeforces problems that never got one.

A bug kept CF threads from being created, and the watcher starts past every
attempt already in the DB, so problems logged before the fix need this one-off
pass. It also links the streamer's accepted submission for each problem, when
CODEFORCES_HANDLE is set, so the threads get their solution replies.

Opens its own short gateway session, so it can run alongside the live bot.

Usage:
    python -m scripts.backfill_cf_threads [--dry-run] [--refresh-titles]

    --dry-run          report what would be posted, touch nothing
    --refresh-titles   re-fetch title/rating/tags from the CF API first (fixes
                       titles logged in Russian before the lang=en fix)
"""

import argparse
import asyncio
import contextlib
import logging

import discord
from sqlalchemy import select

from couchd.core.clients import codeforces as cf_client
from couchd.core.config import settings
from couchd.core.constants import Platform
from couchd.core.db import get_session
from couchd.core.models import CFProblemAttempt, CFProblemPost, GuildConfig
from couchd.core.solutions import upsert_solution
from couchd.platforms.discord.components.cf_problems_forum import sync_cf_problem
from couchd.platforms.discord.components.problems_forum import flush_pending_solutions

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

# user.status count covering the streamer's CF history, not just the latest few.
_SUBMISSION_HISTORY = 1000


async def _unposted_attempts() -> list[CFProblemAttempt]:
    async with get_session() as db:
        return list(
            (
                await db.execute(
                    select(CFProblemAttempt)
                    .outerjoin(
                        CFProblemPost, CFProblemPost.problem_id == CFProblemAttempt.problem_id
                    )
                    .where(CFProblemPost.id.is_(None))
                    .order_by(CFProblemAttempt.id)
                )
            ).scalars().all()
        )


async def _refresh_metadata(attempt: CFProblemAttempt, dry_run: bool) -> None:
    info = await cf_client.fetch_problem(attempt.contest_id, attempt.index)
    if not info:
        log.info("%s: no CF API metadata (gym/edu?), keeping %r", attempt.problem_id, attempt.title)
        return
    log.info("%s: title %r → %r", attempt.problem_id, attempt.title, info["title"])
    if dry_run:
        return
    async with get_session() as db:
        row = await db.get(CFProblemAttempt, attempt.id)
        row.title = info["title"]
        row.rating = info["rating"]
        row.tags = ", ".join(info["tags"]) or None


async def _link_streamer_solutions(problem_ids: set[str], dry_run: bool) -> None:
    submissions = await cf_client.fetch_recent_ac_submissions(
        settings.CODEFORCES_HANDLE, count=_SUBMISSION_HISTORY
    )
    # Newest first, so the first AC seen for a problem is the latest one.
    latest: dict[str, dict] = {}
    for sub in submissions:
        latest.setdefault(f"{sub['contest_id']}{sub['index']}", sub)

    for pid in sorted(problem_ids):
        sub = latest.get(pid)
        if not sub:
            log.info("%s: no accepted submission by %s", pid, settings.CODEFORCES_HANDLE)
            continue
        url = cf_client.submission_url(sub["contest_id"], sub["submission_id"])
        log.info("%s: %s solution %s", pid, "would link" if dry_run else "linking", url)
        if not dry_run:
            await upsert_solution(pid, Platform.TWITCH.value, settings.TWITCH_CHANNEL, url, None)


async def backfill(dry_run: bool, refresh_titles: bool) -> None:
    attempts = await _unposted_attempts()
    problem_ids = {a.problem_id for a in attempts}
    log.info("%d problem(s) without a thread: %s", len(problem_ids), ", ".join(sorted(problem_ids)))

    if refresh_titles:
        for attempt in attempts:
            await _refresh_metadata(attempt, dry_run)
    if problem_ids and settings.CODEFORCES_HANDLE:
        await _link_streamer_solutions(problem_ids, dry_run)
    if dry_run:
        return

    async with get_session() as db:
        config = (
            await db.execute(select(GuildConfig).where(GuildConfig.cf_problems_forum_id.isnot(None)))
        ).scalar_one_or_none()
    if not config:
        log.error("No CF forum configured (/setup cf_problems_forum). Aborting.")
        return

    # A REST-only client gives channels a placeholder guild that py-cord can't build
    # threads from, so connect long enough for the guild to be cached.
    client = discord.Client(intents=discord.Intents(guilds=True))
    await client.login(settings.DISCORD_BOT_TOKEN)
    gateway = asyncio.create_task(client.connect())
    try:
        await client.wait_until_ready()
        forum = client.get_channel(config.cf_problems_forum_id)
        for pid in sorted(problem_ids):
            await sync_cf_problem(forum, pid, client)
        await flush_pending_solutions(forum, client, CFProblemPost.problem_id)
    finally:
        # Stop the gateway first, or its reconnect loop races close() and hits a
        # closed HTTP session.
        gateway.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await gateway
        await client.close()

    remaining = {a.problem_id for a in await _unposted_attempts()}
    log.info("Done: posted %d of %d.", len(problem_ids - remaining), len(problem_ids))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="touch nothing")
    parser.add_argument("--refresh-titles", action="store_true", help="re-fetch CF metadata")
    args = parser.parse_args()
    asyncio.run(backfill(args.dry_run, args.refresh_titles))


if __name__ == "__main__":
    main()
