# couchd/platforms/twitch/utils.py
import logging
from datetime import datetime, timezone

from sqlalchemy import select

from couchd.core.db import get_session
from couchd.core.models import StreamSession
from couchd.core.constants import Platform, TwitchAdDuration

log = logging.getLogger(__name__)


def compute_vod_timestamp(start_time: datetime) -> str:
    """Return a human-readable elapsed time string from stream start."""
    now = datetime.now(timezone.utc)
    if start_time.tzinfo is None:
        start_time = start_time.replace(tzinfo=timezone.utc)
    delta = now - start_time
    hours, remainder = divmod(int(delta.total_seconds()), 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02}h{minutes:02}m{seconds:02}s"


async def get_active_session() -> StreamSession | None:
    """Return the currently active Twitch StreamSession, or None."""
    async with get_session() as db:
        stmt = select(StreamSession).where(
            (StreamSession.is_active == True)
            & (StreamSession.platform == Platform.TWITCH.value)
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()


def clamp_to_ad_duration(seconds: int) -> int:
    """Return the largest valid TwitchAdDuration value that is ≤ seconds."""
    valid = sorted(d.value for d in TwitchAdDuration)
    clamped = valid[0]
    for v in valid:
        if v <= seconds:
            clamped = v
    return clamped
