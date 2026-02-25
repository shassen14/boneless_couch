# couchd/platforms/twitch/main.py
import asyncio
import logging
import twitchio
from twitchio import eventsub
from twitchio.ext import commands
from sqlalchemy import select

import sentry_sdk
from couchd.core.config import settings
from couchd.core.logger import setup_logging
from couchd.core.db import get_session
from couchd.core.models import StreamSession
from couchd.core.constants import ChatMetrics
from couchd.core.clients.twitch import TwitchClient
from couchd.core.clients.youtube import YouTubeRSSClient
from couchd.core.clients.leetcode import LeetCodeClient
from couchd.core.clients.github import GitHubClient
from couchd.platforms.twitch.ads.manager import AdBudgetManager
from couchd.platforms.twitch.ads.scheduler import AdScheduler
from couchd.platforms.twitch.components.metrics_tracker import ChatVelocityTracker
from couchd.platforms.twitch.components.commands import BotCommands
from couchd.platforms.twitch.components.utils import get_active_session

if settings.SENTRY_DSN:
    sentry_sdk.init(dsn=settings.SENTRY_DSN)

setup_logging(webhook_url=settings.BOT_LOGS_WEBHOOK_URL, bot_name="twitch")
log = logging.getLogger(__name__)


class TwitchBot(commands.Bot):
    def __init__(self):
        super().__init__(
            client_id=settings.TWITCH_CLIENT_ID,
            client_secret=settings.TWITCH_CLIENT_SECRET,
            bot_id=settings.TWITCH_BOT_ID,
            owner_id=settings.TWITCH_OWNER_ID,
            prefix="!",
        )
        self.lc_client = LeetCodeClient()
        self.ad_manager = AdBudgetManager(settings.TWITCH_AD_MINUTES_PER_HOUR)
        self.metrics_tracker = ChatVelocityTracker()
        self.github_client = GitHubClient()
        self.twitch_client = TwitchClient()
        self.youtube_client = YouTubeRSSClient() if settings.YOUTUBE_CHANNEL_ID else None
        self.ad_scheduler = AdScheduler(self, self.ad_manager, self.youtube_client)

    async def setup_hook(self) -> None:
        await self.lc_client.load_ratings()

        await self.add_component(
            BotCommands(
                self,
                self.lc_client,
                self.ad_manager,
                self.metrics_tracker,
                self.github_client,
                self.youtube_client,
            )
        )

        # Subscribe to chat on startup (works after token is saved).
        # On first run this will fail gracefully — auth happens via event_oauth_authorized.
        chat_sub = eventsub.ChatMessageSubscription(
            broadcaster_user_id=settings.TWITCH_OWNER_ID,
            user_id=settings.TWITCH_BOT_ID,
        )
        try:
            await self.subscribe_websocket(payload=chat_sub)
            log.info("Subscribed to chat messages via WebSocket.")
        except Exception as e:
            log.warning(
                "Could not subscribe to chat on startup (no saved token?): %s. "
                "Visit http://localhost:4343/oauth to authorize.",
                e,
            )

    async def event_ready(self) -> None:
        log.info("-" * 40)
        log.info("Twitch Bot is ONLINE!")
        log.info(f"Using Owner/Streamer ID: {self.owner_id}")
        log.info(f"Using Bot ID:              {self.bot_id}")
        log.info("-" * 40)
        self.ad_scheduler.start()
        asyncio.create_task(self._run_metrics_loop())

    async def event_oauth_authorized(
        self, payload: twitchio.authentication.UserTokenPayload
    ) -> None:
        """Called on first-time OAuth. Saves the token then subscribes to chat."""
        await self.add_token(payload.access_token, payload.refresh_token)
        log.info(f"✅ Authorization successful for User ID: {payload.user_id}! Tokens saved.")

        chat_sub = eventsub.ChatMessageSubscription(
            broadcaster_user_id=settings.TWITCH_OWNER_ID,
            user_id=settings.TWITCH_BOT_ID,
        )
        try:
            await self.subscribe_websocket(payload=chat_sub)
            log.info("Subscribed to chat messages after OAuth.")
        except Exception as e:
            log.error("Failed to subscribe to chat after OAuth", exc_info=e)

    async def _run_metrics_loop(self) -> None:
        """Periodically update peak viewer count and log high-velocity chat."""
        poll_interval = settings.TWITCH_POLL_RATE_MINUTES * 60

        while True:
            await asyncio.sleep(poll_interval)
            try:
                stream_data = await self.twitch_client.get_stream_status(
                    settings.TWITCH_CHANNEL
                )
                if not stream_data:
                    continue

                viewer_count = stream_data.get("viewer_count", 0)
                session = await get_active_session()

                if session and viewer_count > (session.peak_viewers or 0):
                    async with get_session() as db:
                        stmt = select(StreamSession).where(StreamSession.id == session.id)
                        result = await db.execute(stmt)
                        live_session = result.scalar_one_or_none()
                        if live_session:
                            live_session.peak_viewers = viewer_count
                            await db.commit()
                    log.info("Peak viewers updated: %d.", viewer_count)

                rate = self.metrics_tracker.get_rate_per_minute()
                if rate >= ChatMetrics.HIGH_VELOCITY_THRESHOLD:
                    log.info(
                        "High chat velocity: %.1f msg/min, %d viewers.",
                        rate,
                        viewer_count,
                    )
            except Exception:
                log.error("Error in metrics loop", exc_info=True)


if __name__ == "__main__":
    bot = TwitchBot()
    bot.run()
