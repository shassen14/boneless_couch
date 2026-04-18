# couchd/platforms/twitch/main.py
import asyncio
import json
import logging
from datetime import datetime, timezone
import twitchio
from twitchio import eventsub
from twitchio.ext import commands
from twitchio.ext.commands.exceptions import CommandNotFound
from sqlalchemy import select, text

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
from couchd.platforms.twitch.components.lc_commands import LCCommands
from couchd.platforms.twitch.components.project_commands import ProjectCommands
from couchd.platforms.twitch.components.activity_commands import ActivityCommands
from couchd.platforms.twitch.components.ad_commands import AdCommands
from couchd.platforms.twitch.components.general_commands import GeneralCommands
from couchd.core.utils import get_active_session

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
            scopes=twitchio.Scopes(
                clips_edit=True,
                channel_edit_commercial=True,
                channel_manage_ads=True,
                channel_read_ads=True,
                user_write_chat=True,
                user_read_chat=True,
                channel_bot=True,
                user_bot=True,
                moderator_manage_chat_messages=True,
                channel_manage_broadcast=True,
            ),
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

        await self.add_component(LCCommands(self.lc_client, self.metrics_tracker))
        await self.add_component(ProjectCommands(self.github_client))
        await self.add_component(ActivityCommands())
        await self.add_component(AdCommands(self, self.ad_manager, self.youtube_client))
        await self.add_component(GeneralCommands(self, self.youtube_client))

        # Subscribe to chat and stream lifecycle on startup (works after token is saved).
        # On first run this will fail gracefully — auth happens via event_oauth_authorized.
        chat_sub = eventsub.ChatMessageSubscription(
            broadcaster_user_id=settings.TWITCH_OWNER_ID,
            user_id=settings.TWITCH_BOT_ID,
        )
        stream_online_sub = eventsub.StreamOnlineSubscription(broadcaster_user_id=settings.TWITCH_OWNER_ID)
        stream_offline_sub = eventsub.StreamOfflineSubscription(broadcaster_user_id=settings.TWITCH_OWNER_ID)
        for sub in (chat_sub, stream_online_sub, stream_offline_sub):
            try:
                await self.subscribe_websocket(payload=sub)
                log.info("Subscribed to %s via WebSocket.", sub.__class__.__name__)
            except Exception as e:
                log.warning(
                    "Could not subscribe to %s on startup (no saved token?): %s. "
                    "Visit http://localhost:4343/oauth to authorize.",
                    sub.__class__.__name__,
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
        asyncio.create_task(self._check_live_on_ready())

    async def _check_live_on_ready(self) -> None:
        """On startup, notify Discord if stream is already live (handles mid-stream restarts)."""
        try:
            existing = await get_active_session()
            if existing:
                log.info("Active StreamSession found in DB — skipping startup live-check.")
                return

            stream_data = await self.twitch_client.get_stream_status(settings.TWITCH_CHANNEL)
            if not stream_data:
                log.info("Startup live-check: %s is offline.", settings.TWITCH_CHANNEL)
                return

            log.info("Startup live-check: stream already live — firing stream_online notify.")
            notify_payload = json.dumps({
                "title": stream_data.get("title", ""),
                "category": stream_data.get("game_name", ""),
                "thumbnail_url": stream_data.get("thumbnail_url", ""),
            })
            async with get_session() as db:
                await db.execute(text("SELECT pg_notify('stream_online', :p)"), {"p": notify_payload})
        except Exception:
            log.error("Error in startup live-check", exc_info=True)

    async def event_stream_online(self, payload: twitchio.StreamOnline) -> None:
        if payload.type != "live":
            return
        log.info("Stream online (started_at=%s) — scheduling opener ad.", payload.started_at)
        self.ad_scheduler.fire_opener()

        stream_data = await self.twitch_client.get_stream_status(settings.TWITCH_CHANNEL)
        notify_payload = json.dumps({
            "title": stream_data.get("title", "") if stream_data else "",
            "category": stream_data.get("game_name", "") if stream_data else "",
            "thumbnail_url": stream_data.get("thumbnail_url", "") if stream_data else "",
        })
        async with get_session() as db:
            await db.execute(text("SELECT pg_notify('stream_online', :p)"), {"p": notify_payload})
        log.info("Notified stream_online.")

    async def _trigger_offline(self) -> None:
        async with get_session() as db:
            result = await db.execute(
                select(StreamSession).where(
                    (StreamSession.is_active == True)
                    & (StreamSession.platform == "twitch")
                ).order_by(StreamSession.start_time.desc())
            )
            session = result.scalars().first()
            if not session:
                return
            session.is_active = False
            session.end_time = datetime.now(timezone.utc)
            log.info("Marked StreamSession id=%d as inactive.", session.id)
            await db.execute(
                text("SELECT pg_notify('stream_offline', :p)"),
                {"p": json.dumps({"session_id": session.id})},
            )
        log.info("Notified stream_offline.")

    async def event_stream_offline(self, _payload: twitchio.StreamOffline) -> None:
        log.info("Stream offline — closing session and notifying Discord bot.")
        await self._trigger_offline()

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
        stream_online_sub = eventsub.StreamOnlineSubscription(broadcaster_user_id=settings.TWITCH_OWNER_ID)
        stream_offline_sub = eventsub.StreamOfflineSubscription(broadcaster_user_id=settings.TWITCH_OWNER_ID)
        for sub in (chat_sub, stream_online_sub, stream_offline_sub):
            try:
                await self.subscribe_websocket(payload=sub)
                log.info("Subscribed to %s after OAuth.", sub.__class__.__name__)
            except Exception as e:
                log.error("Failed to subscribe to %s after OAuth", sub.__class__.__name__, exc_info=e)

    async def event_command_error(self, payload: commands.CommandErrorPayload) -> None:
        if isinstance(payload.exception, CommandNotFound):
            return
        log.error("Command error: %s", payload.exception, exc_info=payload.exception)

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
                    if await get_active_session():
                        log.info("Metrics poll: stream offline with active session — triggering offline fallback.")
                        await self._trigger_offline()
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
