# couchd/platforms/twitch/ads/manager.py
import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import select

from couchd.core.db import get_session
from couchd.core.models import StreamEvent
from couchd.core.constants import AdConfig

log = logging.getLogger(__name__)


class AdBudgetManager:
    """Tracks ad spend against the per-hour budget using time-based accumulation."""

    def __init__(self, required_minutes: int):
        self._required_seconds = required_minutes * 60
        self._pending_task: asyncio.Task | None = None

    async def get_remaining(self, session_id: int, session_start: datetime) -> int:
        """
        Ad seconds accumulated since the last ad (or stream start), capped at the hourly budget.
        Budget accrues at required/hour. 30 min after a 3-min-budget ad → 90s available.
        """
        last_ad = await self.get_last_ad_time(session_id)
        reference = last_ad if last_ad else session_start
        if reference.tzinfo is None:
            reference = reference.replace(tzinfo=timezone.utc)
        elapsed = min(
            (datetime.now(timezone.utc) - reference).total_seconds(),
            AdConfig.WINDOW_SECONDS,
        )
        return int(elapsed * self._required_seconds / AdConfig.WINDOW_SECONDS)

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
