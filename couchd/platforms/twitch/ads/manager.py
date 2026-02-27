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
    """Tracks ad spend against the per-hour budget using fixed session-aligned blocks."""

    def __init__(self, required_minutes: int):
        self._required_seconds = required_minutes * 60
        self._pending_task: asyncio.Task | None = None

    def block_start(self, session_start: datetime) -> datetime:
        """Start of the current fixed 60-minute block for this session."""
        now = datetime.now(timezone.utc)
        if session_start.tzinfo is None:
            session_start = session_start.replace(tzinfo=timezone.utc)
        block_num = int((now - session_start).total_seconds() // AdConfig.WINDOW_SECONDS)
        return session_start + timedelta(seconds=block_num * AdConfig.WINDOW_SECONDS)

    async def get_seconds_used(self, session_id: int, session_start: datetime) -> int:
        """Sum ad seconds logged in the current hour block."""
        start = self.block_start(session_start)
        end = start + timedelta(seconds=AdConfig.WINDOW_SECONDS)
        async with get_session() as db:
            stmt = select(
                func.coalesce(func.sum(cast(StreamEvent.notes, SAInteger)), 0)
            ).where(
                StreamEvent.session_id == session_id,
                StreamEvent.event_type == "ad",
                StreamEvent.timestamp >= start,
                StreamEvent.timestamp < end,
            )
            result = await db.execute(stmt)
            return result.scalar_one()

    async def get_remaining(self, session_id: int, session_start: datetime) -> int:
        """Pro-rated ad seconds still owed in the current hour block.

        Grows linearly from 0 to required_seconds over the block.
        Returns 0 if ads already run exceed the pro-rated amount (ahead of schedule).
        """
        if session_start.tzinfo is None:
            session_start = session_start.replace(tzinfo=timezone.utc)
        start = self.block_start(session_start)
        elapsed_in_block = (datetime.now(timezone.utc) - start).total_seconds()
        pro_rated = round(elapsed_in_block / AdConfig.WINDOW_SECONDS * self._required_seconds)
        used = await self.get_seconds_used(session_id, session_start)
        return max(0, pro_rated - used)

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
