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
from couchd.core.constants import ChatMetrics, HoldSource
from couchd.core.moderation import ModerationEngine
from couchd.core.clients.twitch import TwitchClient
from couchd.core.clients.emotes import EmoteClient
from couchd.core.clients.youtube import YouTubeRSSClient
from couchd.core.clients.leetcode import LeetCodeClient
from couchd.core.clients.github import GitHubClient
from couchd.core.clients import veil
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
                # Chat
                user_read_chat=True,
                user_write_chat=True,
                user_bot=True,
                channel_bot=True,
                # Ads
                clips_edit=True,
                channel_edit_commercial=True,
                channel_manage_ads=True,
                channel_read_ads=True,
                # Mod tools
                moderator_manage_chat_messages=True,
                moderator_manage_banned_users=True,
                moderator_manage_announcements=True,
                moderator_manage_chat_settings=True,
                moderator_manage_shoutouts=True,
                moderator_manage_automod=True,
                # Stream management
                channel_manage_broadcast=True,
                channel_manage_raids=True,
                # Alerts / EventSub
                channel_read_subscriptions=True,
                bits_read=True,
                channel_read_redemptions=True,
                channel_manage_redemptions=True,
                # Polls / predictions / goals / hype train
                channel_read_polls=True,
                channel_read_predictions=True,
                channel_read_goals=True,
                channel_read_hype_train=True,
                channel_read_vips=True,
                # Whispers
                user_manage_whispers=True,
                # Read-only moderation data
                moderation_read=True,
                moderator_read_followers=True,
                moderator_read_chatters=True,
            ),
        )
        self.lc_client = LeetCodeClient()
        self.ad_manager = AdBudgetManager(settings.TWITCH_AD_MINUTES_PER_HOUR)
        self.metrics_tracker = ChatVelocityTracker()
        self.github_client = GitHubClient()
        self.twitch_client = TwitchClient()
        self.emote_client = EmoteClient()
        self.youtube_client = YouTubeRSSClient() if settings.YOUTUBE_CHANNEL_ID else None
        self.ad_scheduler = AdScheduler(self, self.ad_manager, self.youtube_client)
        self.mod_engine = ModerationEngine(settings.MODERATION_PATTERNS)

    async def setup_hook(self) -> None:
        await self.lc_client.load_ratings()

        await self.add_component(LCCommands(self.lc_client, self.metrics_tracker, self.mod_engine))
        await self.add_component(ProjectCommands(self.github_client))
        await self.add_component(ActivityCommands())
        await self.add_component(AdCommands(self, self.ad_manager, self.youtube_client))
        await self.add_component(GeneralCommands(self, self.youtube_client))

        # Subscribe to chat and stream lifecycle on startup (works after token is saved).
        # On first run this will fail gracefully — auth happens via event_oauth_authorized.
        owner = settings.TWITCH_OWNER_ID
        tagged = [(s, None) for s in self._build_bot_subscriptions()] + [
            (s, owner) for s in self._build_owner_subscriptions()
        ]
        for sub, token_for in tagged:
            try:
                await self.subscribe_websocket(payload=sub, token_for=token_for)
                log.info("Subscribed to %s via WebSocket.", sub.__class__.__name__)
            except Exception as e:
                log.warning(
                    "Could not subscribe to %s on startup: %s. "
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
        asyncio.create_task(veil.listen_decisions(
            self._on_modqueue_decision,
            on_connect=self._push_emotes,
        ))

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

    async def _push_emotes(self) -> None:
        try:
            channel_id = await self.twitch_client.get_user_id(settings.TWITCH_CHANNEL)
            twitch_global, twitch_channel, third_party = await asyncio.gather(
                self.twitch_client.get_global_emotes(),
                self.twitch_client.get_channel_emotes(channel_id or ""),
                self.emote_client.fetch_all(settings.TWITCH_CHANNEL, channel_id or ""),
            )
            emotes = {**twitch_global, **twitch_channel, **third_party}
            await veil.post_event("emotes.update", {"emote_map": emotes})
            log.info("Pushed %d emotes to veil.", len(emotes))
        except Exception:
            log.error("Failed to push emotes to veil.", exc_info=True)

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

    def _build_bot_subscriptions(self) -> list:
        """Subscriptions that use the bot's user token."""
        owner = settings.TWITCH_OWNER_ID
        return [
            eventsub.ChatMessageSubscription(broadcaster_user_id=owner, user_id=settings.TWITCH_BOT_ID),
            eventsub.ChatMessageDeleteSubscription(broadcaster_user_id=owner, user_id=settings.TWITCH_BOT_ID),
            eventsub.ChatClearUserMessagesSubscription(broadcaster_user_id=owner, user_id=settings.TWITCH_BOT_ID),
        ]

    def _build_owner_subscriptions(self) -> list:
        """Subscriptions that require the broadcaster's user token."""
        owner = settings.TWITCH_OWNER_ID
        return [
            eventsub.StreamOnlineSubscription(broadcaster_user_id=owner),
            eventsub.StreamOfflineSubscription(broadcaster_user_id=owner),
            eventsub.ChannelSubscribeSubscription(broadcaster_user_id=owner),
            eventsub.ChannelSubscribeMessageSubscription(broadcaster_user_id=owner),
            eventsub.ChannelSubscriptionGiftSubscription(broadcaster_user_id=owner),
            eventsub.ChannelCheerSubscription(broadcaster_user_id=owner),
            eventsub.ChannelRaidSubscription(to_broadcaster_user_id=owner),
            eventsub.ChannelPointsRedeemAddSubscription(broadcaster_user_id=owner),
            eventsub.AutomodMessageHoldSubscription(broadcaster_user_id=owner, moderator_user_id=owner),
            eventsub.AutomodMessageUpdateSubscription(broadcaster_user_id=owner, moderator_user_id=owner),
            eventsub.ChannelFollowSubscription(broadcaster_user_id=owner, moderator_user_id=owner),
        ]

    async def event_message_delete(self, payload: twitchio.ChatMessageDelete) -> None:
        await veil.post_event("twitch.chat.message.delete", {"message_id": payload.message_id})

    async def event_chat_clear_user(self, payload: twitchio.ChannelChatClearUserMessages) -> None:
        await veil.post_event("twitch.chat.clear_user", {"username": payload.user.name})

    async def event_automod_message_hold(self, payload: twitchio.AutomodMessageHold) -> None:
        mid = payload.message_id
        if self.mod_engine.has(mid):
            pending = self.mod_engine.add_hold_source(mid, HoldSource.TWITCH_AUTOMOD)
            if pending:
                await veil.post_event("modqueue.update", {
                    "message_id": mid,
                    "hold_sources": pending.hold_sources,
                })
        else:
            chat_payload = {
                "message_id": mid,
                "username": payload.user.name,
                "display_name": payload.user.display_name,
                "message": payload.text,
                "color": "",
                "badges": [],
                "platform": "twitch",
            }
            self.mod_engine.add_pending(mid, chat_payload, HoldSource.TWITCH_AUTOMOD)
            await veil.post_event("modqueue.pending", {
                **chat_payload,
                "hold_sources": [HoldSource.TWITCH_AUTOMOD],
            })

    async def event_automod_message_update(self, payload: twitchio.AutomodMessageUpdate) -> None:
        mid = payload.message_id
        if not self.mod_engine.has(mid):
            return
        self.mod_engine.pop(mid)
        await veil.post_event("modqueue.resolved", {
            "message_id": mid,
            "resolution": payload.status.lower(),
        })

    async def _on_modqueue_decision(self, message_id: str, decision: str, platform: str) -> None:
        if platform != "twitch":
            return
        pending = self.mod_engine.get(message_id)
        if not pending:
            return
        if HoldSource.TWITCH_AUTOMOD in pending.hold_sources:
            try:
                users = await self.fetch_users(ids=[int(settings.TWITCH_OWNER_ID)])
                if users:
                    owner = users[0]
                    if decision == "approve":
                        await owner.approve_automod_messages(message_id)
                        log.info("AutoMod approved message %s via Twitch API.", message_id)
                    else:
                        await owner.deny_automod_messages(message_id)
                        log.info("AutoMod denied message %s via Twitch API.", message_id)
            except Exception:
                log.error("Failed to call Twitch AutoMod API for %s", message_id, exc_info=True)
        self.mod_engine.pop(message_id)

    async def event_subscription(self, payload: twitchio.ChannelSubscribe) -> None:
        if payload.gift:
            return
        await veil.post_event("twitch.sub", {
            "username": payload.user.name,
            "display_name": payload.user.display_name,
            "tier": payload.tier,
            "is_gift": False,
        })

    async def event_subscription_message(self, payload: twitchio.ChannelSubscriptionMessage) -> None:
        await veil.post_event("twitch.resub", {
            "username": payload.user.name,
            "display_name": payload.user.display_name,
            "tier": payload.tier,
            "cumulative_months": payload.cumulative_months,
            "streak_months": payload.streak_months or 0,
            "message": payload.text,
        })

    async def event_subscription_gift(self, payload: twitchio.ChannelSubscriptionGift) -> None:
        gifter = payload.user
        await veil.post_event("twitch.giftbomb", {
            "gifter_username": gifter.name if gifter else "anonymous",
            "gifter_display_name": gifter.display_name if gifter else "Anonymous",
            "count": payload.total,
            "tier": payload.tier,
        })

    async def event_cheer(self, payload: twitchio.ChannelCheer) -> None:
        user = payload.user
        await veil.post_event("twitch.bits", {
            "username": user.name if user else "anonymous",
            "display_name": user.display_name if user else "Anonymous",
            "bits": payload.bits,
            "message": payload.message,
        })

    async def event_raid(self, payload: twitchio.ChannelRaid) -> None:
        await veil.post_event("twitch.raid", {
            "from_username": payload.from_broadcaster.name,
            "from_display_name": payload.from_broadcaster.display_name,
            "viewer_count": payload.viewer_count,
        })

    async def event_channel_follow(self, payload: twitchio.ChannelFollow) -> None:
        await veil.post_event("twitch.follower", {
            "username": payload.user.name,
            "display_name": payload.user.display_name,
        })

    async def event_custom_redemption_add(self, payload: twitchio.ChannelPointsRedemptionAdd) -> None:
        await veil.post_event("twitch.channel_point_redeem", {
            "username": payload.user.name,
            "display_name": payload.user.display_name,
            "reward_id": payload.reward.id,
            "reward_title": payload.reward.title,
            "reward_cost": payload.reward.cost,
            "user_input": payload.user_input,
        })

    async def event_oauth_authorized(
        self, payload: twitchio.authentication.UserTokenPayload
    ) -> None:
        await self.add_token(payload.access_token, payload.refresh_token)
        log.info("Authorization successful for User ID: %s. Tokens saved.", payload.user_id)

        is_owner = str(payload.user_id) == str(settings.TWITCH_OWNER_ID)
        if is_owner:
            tagged = [(s, settings.TWITCH_OWNER_ID) for s in self._build_owner_subscriptions()]
        else:
            tagged = [(s, None) for s in self._build_bot_subscriptions()]

        for sub, token_for in tagged:
            try:
                await self.subscribe_websocket(payload=sub, token_for=token_for)
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
