# couchd/core/utils.py
from datetime import datetime, timezone

from sqlalchemy import func, select

from couchd.core.config import settings
from couchd.core.db import get_session
from couchd.core.models import StreamSession, ViewerInteraction
from couchd.core.constants import Platform, InteractionType


def compute_vod_timestamp(start_time: datetime) -> str:
    now = datetime.now(timezone.utc)
    if start_time.tzinfo is None:
        start_time = start_time.replace(tzinfo=timezone.utc)
    delta = now - start_time
    hours, remainder = divmod(int(delta.total_seconds()), 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02}h{minutes:02}m{seconds:02}s"


async def get_active_session(platform: Platform = Platform.TWITCH) -> StreamSession | None:
    async with get_session() as db:
        result = await db.execute(
            select(StreamSession)
            .where(
                (StreamSession.is_active == True)
                & (StreamSession.platform == platform.value)
            )
            .order_by(StreamSession.start_time.desc())
        )
        return result.scalars().first()


async def get_overlay_stats() -> dict:
    # An AsyncSession wraps one connection and is not safe for concurrent use;
    # asyncpg serializes a single connection's queries at the wire anyway, so
    # these run sequentially (gather here would corrupt the session's state).
    async with get_session() as db:
        last_follow = (await db.execute(
            select(ViewerInteraction)
            .where(ViewerInteraction.interaction_type == InteractionType.FOLLOW)
            .order_by(ViewerInteraction.timestamp.desc()).limit(1)
        )).scalars().first()
        last_raid = (await db.execute(
            select(ViewerInteraction)
            .where(ViewerInteraction.interaction_type == InteractionType.RAID)
            .order_by(ViewerInteraction.timestamp.desc()).limit(1)
        )).scalars().first()
        last_bits = (await db.execute(
            select(ViewerInteraction)
            .where(ViewerInteraction.interaction_type == InteractionType.BITS)
            .order_by(ViewerInteraction.timestamp.desc()).limit(1)
        )).scalars().first()
        recent_subs = (await db.execute(
            select(ViewerInteraction)
            .where(ViewerInteraction.interaction_type.in_([
                InteractionType.SUB, InteractionType.RESUB, InteractionType.GIFTBOMB,
            ]))
            .order_by(ViewerInteraction.timestamp.desc()).limit(5)
        )).scalars().all()
        longest_subs = (await db.execute(
            select(
                ViewerInteraction.username,
                func.max(ViewerInteraction.display_name).label("display_name"),
                func.count().label("months"),
            )
            .where(
                ViewerInteraction.interaction_type.in_([InteractionType.SUB, InteractionType.RESUB])
                & (ViewerInteraction.username != settings.TWITCH_CHANNEL)
            )
            .group_by(ViewerInteraction.username)
            .order_by(func.count().desc())
            .limit(5)
        )).all()

    def _row(v: ViewerInteraction) -> dict:
        return {
            "username": v.username, "display_name": v.display_name,
            "interaction_type": v.interaction_type, "tier": v.tier,
            "cumulative_months": v.cumulative_months, "gift_count": v.gift_count,
            "bits": v.bits, "viewer_count": v.viewer_count,
            "timestamp": v.timestamp.isoformat(),
        }

    return {
        "last_follower": _row(last_follow) if last_follow else {},
        "last_raider": _row(last_raid) if last_raid else {},
        "last_bits": _row(last_bits) if last_bits else {},
        "recent_subs": [_row(r) for r in recent_subs],
        "longest_subs": [{"username": r.username, "display_name": r.display_name, "cumulative_months": r.months} for r in longest_subs],
    }
