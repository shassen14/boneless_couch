# couchd/core/vod.py
"""Resolving a StreamSession to its Twitch archive VOD URL.

``StreamSession.vod_url`` is what content_os downloads to scaffold an editing
project — without it a scaffold job silently skips the session. Twitch does not
hand us the VOD id on the go-live event, so we look it up afterwards by matching
the archive video's ``created_at`` against the session's ``start_time``.

Kept separate from the Discord cog so the live path and the backfill script run
identical matching logic.
"""
import logging
from datetime import datetime, timezone

from couchd.core.clients.twitch import TwitchClient
from couchd.core.constants import TwitchVodConfig

log = logging.getLogger(__name__)


def _parse_created_at(value: str | None) -> datetime | None:
    """Twitch returns RFC3339 with a trailing Z."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def select_vod_for_session(
    videos: list[dict],
    start_time: datetime,
    *,
    tolerance_seconds: int = TwitchVodConfig.MATCH_TOLERANCE_SECONDS,
) -> dict | None:
    """Pick the archive video that belongs to the stream starting at ``start_time``.

    Twitch stamps an archive's ``created_at`` with the moment the broadcast went
    live, so the right VOD is the nearest one within ``tolerance_seconds``.
    Returns the raw video dict, or None when nothing is close enough — which is
    the normal answer for a stream whose VOD has expired or was never saved.
    """
    start = _aware(start_time)
    if start is None:
        return None

    best: dict | None = None
    best_delta = float("inf")
    for video in videos:
        created = _parse_created_at(video.get("created_at"))
        if created is None:
            continue
        delta = abs((created - start).total_seconds())
        if delta <= tolerance_seconds and delta < best_delta:
            best, best_delta = video, delta

    if best is not None:
        log.debug(
            "Matched VOD %s to session start %s (%.0fs apart).",
            best.get("id"),
            start.isoformat(),
            best_delta,
        )
    return best


async def resolve_vod_url(
    client: TwitchClient, username: str, start_time: datetime
) -> str | None:
    """Look up the archive VOD URL for a stream that started at ``start_time``.

    Best-effort: returns None on any failure (no user id, API error, no match)
    rather than raising, because a missing VOD must never break the stream-end
    lifecycle. The backfill script can always fill it in later.
    """
    user_id = await client.get_user_id(username)
    if not user_id:
        log.warning("Could not resolve Twitch user id for %s; no VOD lookup.", username)
        return None

    videos = await client.get_videos(user_id)
    if not videos:
        log.info("No archive VODs returned for %s.", username)
        return None

    match = select_vod_for_session(videos, start_time)
    if match is None:
        log.info("No archive VOD matched session starting %s.", start_time)
        return None
    return match.get("url")
