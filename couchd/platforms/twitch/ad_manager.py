# couchd/platforms/twitch/ad_manager.py
import asyncio
import logging
from datetime import datetime, timezone, timedelta

from sqlalchemy import func, cast, Integer as SAInteger, select

from couchd.core.db import get_session
from couchd.core.models import StreamEvent
from couchd.core.constants import AdConfig

log = logging.getLogger(__name__)


class AdBudgetManager:
    """Tracks ad spend against the per-hour budget and schedules auto-ads."""

    def __init__(self, required_minutes: int):
        self._required_seconds = required_minutes * 60
        self._pending_task: asyncio.Task | None = None

    async def get_seconds_used(self, session_id: int) -> int:
        """Sum ad durations (stored as seconds in platform_id) within the rolling window."""
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=AdConfig.WINDOW_SECONDS)
        async with get_session() as db:
            stmt = select(
                func.coalesce(
                    func.sum(cast(StreamEvent.platform_id, SAInteger)), 0
                )
            ).where(
                StreamEvent.session_id == session_id,
                StreamEvent.event_type == "ad",
                StreamEvent.timestamp > cutoff,
            )
            result = await db.execute(stmt)
            return result.scalar_one()

    async def get_remaining(self, session_id: int) -> int:
        """Return how many seconds of ads still need to run this window."""
        used = await self.get_seconds_used(session_id)
        return max(0, self._required_seconds - used)

    async def get_last_ad_time(self, session_id: int) -> datetime | None:
        """Return the timestamp of the most recent ad event in this session."""
        async with get_session() as db:
            stmt = select(func.max(StreamEvent.timestamp)).where(
                StreamEvent.session_id == session_id,
                StreamEvent.event_type == "ad",
            )
            result = await db.execute(stmt)
            return result.scalar_one_or_none()

    async def log_ad(
        self, session_id: int, duration_seconds: int, vod_timestamp: str
    ) -> None:
        """Write an ad event to the DB."""
        minutes = duration_seconds // 60
        async with get_session() as db:
            event = StreamEvent(
                session_id=session_id,
                event_type="ad",
                title=f"{minutes}m ad",
                platform_id=str(duration_seconds),
                vod_timestamp=vod_timestamp,
            )
            db.add(event)
            await db.commit()
        log.info("Logged ad event: %ds at %s", duration_seconds, vod_timestamp)

    def cancel_pending(self) -> None:
        """Cancel the scheduled auto-ad task if one is waiting."""
        if self._pending_task and not self._pending_task.done():
            self._pending_task.cancel()
        self._pending_task = None

    def has_pending(self) -> bool:
        """Return True if an auto-ad task is currently scheduled."""
        return self._pending_task is not None and not self._pending_task.done()
