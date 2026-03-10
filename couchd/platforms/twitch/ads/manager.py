# couchd/platforms/twitch/ads/manager.py
import asyncio
import logging
from datetime import datetime, timezone, timedelta

from sqlalchemy import func, cast, Integer as SAInteger, select

from couchd.core.db import get_session
from couchd.core.models import StreamEvent
from couchd.core.constants import AdConfig

log = logging.getLogger(__name__)


class AdBudgetManager:
    """Tracks ad spend against the per-hour budget using a rolling 60-minute window."""

    def __init__(self, required_minutes: int):
        self._required_seconds = required_minutes * 60
        self._pending_task: asyncio.Task | None = None

    async def get_seconds_used(self, session_id: int) -> int:
        """Sum ad seconds logged in the last 60-minute rolling window."""
        since = datetime.now(timezone.utc) - timedelta(seconds=AdConfig.WINDOW_SECONDS)
        async with get_session() as db:
            stmt = select(
                func.coalesce(func.sum(cast(StreamEvent.notes, SAInteger)), 0)
            ).where(
                StreamEvent.session_id == session_id,
                StreamEvent.event_type == "ad",
                StreamEvent.timestamp >= since,
            )
            result = await db.execute(stmt)
            return result.scalar_one()

    async def get_remaining(self, session_id: int) -> int:
        """Ad seconds still owed in the current rolling window."""
        used = await self.get_seconds_used(session_id)
        return max(0, self._required_seconds - used)

    async def get_last_ad_time(self, session_id: int) -> datetime | None:
        """Timestamp of the most recent ad event for this session, or None."""
        async with get_session() as db:
            stmt = (
                select(StreamEvent.timestamp)
                .where(
                    StreamEvent.session_id == session_id,
                    StreamEvent.event_type == "ad",
                )
                .order_by(StreamEvent.timestamp.desc())
                .limit(1)
            )
            result = await db.execute(stmt)
            return result.scalar_one_or_none()

    async def log_ad(
        self, session_id: int, duration_seconds: int, vod_timestamp: str
    ) -> None:
        """Write an ad event to the DB. Duration stored in notes for budget queries."""
        async with get_session() as db:
            db.add(StreamEvent(
                session_id=session_id,
                event_type="ad",
                notes=str(duration_seconds),
            ))
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
