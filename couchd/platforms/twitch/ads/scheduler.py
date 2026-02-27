# couchd/platforms/twitch/ads/scheduler.py
import asyncio
import logging
from datetime import datetime, timezone

from couchd.core.config import settings
from couchd.core.models import StreamSession
from couchd.core.constants import AdConfig
from couchd.core.clients.youtube import YouTubeRSSClient
from couchd.platforms.twitch.ads.manager import AdBudgetManager
from couchd.platforms.twitch.components.utils import get_active_session, compute_vod_timestamp, clamp_to_ad_duration, send_chat_message
from couchd.platforms.twitch.ads.messages import pick_ad_message

log = logging.getLogger(__name__)


class AdScheduler:
    """
    Safety-net background scheduler: auto-fires ads so the hourly budget
    is met before the 60-minute window closes.
    """

    def __init__(self, bot, ad_manager: AdBudgetManager, youtube_client: YouTubeRSSClient | None):
        self._bot = bot
        self._ad_manager = ad_manager
        self._youtube_client = youtube_client

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

                remaining = await self._ad_manager.get_remaining(session.id, session.start_time)
                if remaining == 0:
                    continue

                # Fire when block time elapsed is close enough that the ad must run now.
                block_start = self._ad_manager.block_start(session.start_time)
                elapsed_in_block = (datetime.now(timezone.utc) - block_start).total_seconds()
                fire_threshold = AdConfig.WINDOW_SECONDS - remaining
                if elapsed_in_block < fire_threshold:
                    continue

                log.info(
                    "Ad scheduler: %.0fs into block, threshold %.0fs — scheduling auto-ad (%ds).",
                    elapsed_in_block,
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
            await send_chat_message(
                self._bot,
                f"⏰ Ad break in {AdConfig.WARNING_SECONDS}s — time to stretch!",
            )
            await asyncio.sleep(AdConfig.WARNING_SECONDS)

            clamped = clamp_to_ad_duration(duration_seconds)
            users = await self._bot.fetch_users(logins=[settings.TWITCH_CHANNEL])
            if not users:
                log.warning("_warn_then_ad: could not fetch channel user to start commercial.")
                return
            await users[0].start_commercial(length=clamped)

            vod_ts = compute_vod_timestamp(session.start_time)
            await self._ad_manager.log_ad(session.id, clamped, vod_ts)

            minutes = clamped // 60
            await send_chat_message(self._bot, f"🎬 Auto ad running ({minutes}m). Back soon!")
            log.info("Auto-ad complete: %ds at %s.", clamped, vod_ts)

            latest_video = await self._youtube_client.get_latest_video() if self._youtube_client else None
            ad_msg = pick_ad_message(latest_video)
            if ad_msg:
                await send_chat_message(self._bot, ad_msg)
        except asyncio.CancelledError:
            log.info("Auto-ad task cancelled (manual ad ran first).")
        except Exception:
            log.error("Error in _warn_then_ad", exc_info=True)
