"""Backfill StreamSession.vod_url from Twitch's archive video list.

Existing sessions predate VOD-URL recording, so content_os skips them when
scaffolding. This walks recent sessions, matches each to its Twitch archive VOD
by start time, and writes the URL back.

Twitch archives expire (14 days on the base tier, 60 for Partner/Turbo), so
sessions older than the retention window will legitimately find no match.

Usage:
    python -m scripts.backfill_vod_urls [--dry-run] [--limit N] [--force]

    --dry-run   report what would change, write nothing
    --limit N   only consider the N most recent sessions (default 50)
    --force     also re-resolve sessions that already have a vod_url
"""

import argparse
import asyncio
import logging

from sqlalchemy import select

from couchd.core.clients.twitch import TwitchClient
from couchd.core.config import settings
from couchd.core.constants import Platform, TwitchVodConfig
from couchd.core.db import get_session
from couchd.core.models import StreamSession
from couchd.core.vod import select_vod_for_session

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

_DEFAULT_LIMIT = 50


async def _fetch_sessions(limit: int, force: bool) -> list[StreamSession]:
    async with get_session() as db:
        query = (
            select(StreamSession)
            .where(StreamSession.platform == Platform.TWITCH.value)
            .order_by(StreamSession.start_time.desc())
            .limit(limit)
        )
        if not force:
            query = query.where(StreamSession.vod_url.is_(None))
        rows = (await db.execute(query)).scalars().all()
        # Detach: we re-fetch per-row in the write pass so each update is its
        # own short transaction rather than one long-held session.
        db.expunge_all()
        return list(rows)


async def backfill(limit: int, dry_run: bool, force: bool) -> None:
    sessions = await _fetch_sessions(limit, force)
    if not sessions:
        log.info("No sessions need a vod_url. Nothing to do.")
        return
    log.info("Considering %d session(s).", len(sessions))

    client = TwitchClient()
    channel = settings.TWITCH_CHANNEL
    user_id = await client.get_user_id(channel)
    if not user_id:
        log.error("Could not resolve Twitch user id for %s. Aborting.", channel)
        return

    # One API call covers every session: Twitch returns the most recent archives
    # and each session picks its own match out of that list.
    videos = await client.get_videos(user_id, first=TwitchVodConfig.LOOKUP_LIMIT)
    if not videos:
        log.error("Twitch returned no archive videos for %s. Aborting.", channel)
        return
    log.info("Fetched %d archive video(s) from Twitch.", len(videos))

    matched = 0
    for stream_session in sessions:
        match = select_vod_for_session(videos, stream_session.start_time)
        if match is None:
            log.info(
                "session %-4d %s → no match (likely expired)",
                stream_session.id,
                stream_session.start_time,
            )
            continue

        url = match.get("url")
        matched += 1
        if dry_run:
            log.info("session %-4d → would set %s", stream_session.id, url)
            continue

        async with get_session() as db:
            row = await db.get(StreamSession, stream_session.id)
            if row is not None:
                row.vod_url = url
        log.info("session %-4d → set %s", stream_session.id, url)

    verb = "would update" if dry_run else "updated"
    log.info("Done: %s %d of %d session(s).", verb, matched, len(sessions))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="write nothing")
    parser.add_argument("--limit", type=int, default=_DEFAULT_LIMIT)
    parser.add_argument(
        "--force", action="store_true", help="re-resolve sessions that already have a URL"
    )
    args = parser.parse_args()
    asyncio.run(backfill(args.limit, args.dry_run, args.force))


if __name__ == "__main__":
    main()
