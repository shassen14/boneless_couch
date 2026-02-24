# couchd/platforms/twitch/ad_scheduler.py
import asyncio
import logging
from datetime import datetime, timezone

from couchd.core.config import settings
from couchd.core.models import StreamSession
from couchd.core.constants import AdConfig
from couchd.platforms.twitch.ad_manager import AdBudgetManager
from couchd.platforms.twitch.utils import get_active_session, compute_vod_timestamp, clamp_to_ad_duration

log = logging.getLogger(__name__)


class AdScheduler:
    """
    Safety-net background scheduler: auto-fires ads so the hourly budget
    is met before the 60-minute window closes.
    """

    def __init__(self, bot, ad_manager: AdBudgetManager):
        self._bot = bot
        self._ad_manager = ad_manager

    def start(self) -> None:
        asyncio.create_task(self._run_loop())

    async def _run_loop(self) -> None:
        await asyncio.sleep(AdConfig.MIN_STREAM_AGE_SECONDS)

        while True:
            await asyncio.sleep(60)
            try:
                session = await get_active_session()
                if not session or self._ad_manager.has_pending():
                    continue

                remaining = await self._ad_manager.get_remaining(session.id)
                if remaining == 0:
                    continue

                # How long after the last ad to wait so the new ad finishes
                # right at the 60-min mark.
                fire_threshold = AdConfig.WINDOW_SECONDS - remaining

                last_ad = await self._ad_manager.get_last_ad_time(session.id)
                reference = last_ad if last_ad else session.start_time
                if reference.tzinfo is None:
                    reference = reference.replace(tzinfo=timezone.utc)

                elapsed = (datetime.now(timezone.utc) - reference).total_seconds()
                if elapsed < fire_threshold:
                    continue

                log.info(
                    "Ad scheduler: %.0fs elapsed, threshold %.0fs — scheduling auto-ad (%ds).",
                    elapsed,
                    fire_threshold,
                    remaining,
                )
                self._ad_manager._pending_task = asyncio.create_task(
                    self._warn_then_ad(session, remaining)
                )
            except Exception:
                log.error("Error in ad scheduler loop", exc_info=True)

    async def _warn_then_ad(self, session: StreamSession, duration_seconds: int) -> None:
        """Warn chat, wait, then fire the auto-ad."""
        try:
            users = await self._bot.fetch_users(names=[settings.TWITCH_CHANNEL])
            if not users:
                log.warning("_warn_then_ad: could not fetch channel user.")
                return
            channel_user = users[0]

            await channel_user.send_message(
                sender_id=settings.TWITCH_BOT_ID,
                message=f"⏰ Ad break in {AdConfig.WARNING_SECONDS}s — time to stretch!",
            )
            await asyncio.sleep(AdConfig.WARNING_SECONDS)

            clamped = clamp_to_ad_duration(duration_seconds)
            await channel_user.start_commercial(length=clamped)

            vod_ts = compute_vod_timestamp(session.start_time)
            await self._ad_manager.log_ad(session.id, clamped, vod_ts)

            minutes = clamped // 60
            await channel_user.send_message(
                sender_id=settings.TWITCH_BOT_ID,
                message=f"🎬 Auto ad running ({minutes}m). Back soon!",
            )
            log.info("Auto-ad complete: %ds at %s.", clamped, vod_ts)
        except asyncio.CancelledError:
            log.info("Auto-ad task cancelled (manual ad ran first).")
        except Exception:
            log.error("Error in _warn_then_ad", exc_info=True)
