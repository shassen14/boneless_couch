# couchd/core/utils.py
from datetime import datetime, timezone

from sqlalchemy import select

from couchd.core.db import get_session
from couchd.core.models import StreamSession
from couchd.core.constants import Platform


def compute_vod_timestamp(start_time: datetime) -> str:
    now = datetime.now(timezone.utc)
    if start_time.tzinfo is None:
        start_time = start_time.replace(tzinfo=timezone.utc)
    delta = now - start_time
    hours, remainder = divmod(int(delta.total_seconds()), 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02}h{minutes:02}m{seconds:02}s"


async def get_active_session() -> StreamSession | None:
    async with get_session() as db:
        result = await db.execute(
            select(StreamSession)
            .where(
                (StreamSession.is_active == True)
                & (StreamSession.platform == Platform.TWITCH.value)
            )
            .order_by(StreamSession.start_time.desc())
        )
        return result.scalars().first()
