# couchd/platforms/twitch/main.py
import logging
import twitchio
from twitchio import eventsub
from twitchio.ext import commands
from sqlalchemy import select
from datetime import datetime, timezone

from couchd.core.config import settings
from couchd.core.logger import setup_logging
from couchd.core.db import get_session
from couchd.core.models import StreamSession, StreamEvent
from couchd.core.constants import Platform, TwitchAdDuration

# Initialize centralized logging
setup_logging()
log = logging.getLogger(__name__)


class BotCommands(commands.Component):
    """Holds all the chat commands for the bot."""

    def __init__(self, bot: commands.AutoBot):
        self.bot = bot

    async def get_active_session(self):
        """Helper to find the active StreamSession in our DB."""
        async with get_session() as session:
            stmt = select(StreamSession).where(
                (StreamSession.is_active == True)
                & (StreamSession.platform == Platform.TWITCH.value)
            )
            result = await session.execute(stmt)
            # We return the scalar, but note: detached objects can be tricky.
            # Usually, we just want the ID to create events.
            return result.scalar_one_or_none()

    # --- DIAGNOSTIC LISTENERS ---
    @commands.Component.listener()
    async def event_eventsub_subscription_ok(
        self, payload: eventsub.SubscriptionPayload
    ) -> None:
        log.info(
            f"✅ EventSub subscription is OK! Type: {payload.type}, Status: {payload.status}"
        )

    @commands.Component.listener()
    async def event_eventsub_subscription_error(
        self, payload: eventsub.SubscriptionPayload
    ) -> None:
        log.error(
            f"❌ EventSub subscription FAILED! Type: {payload.type}, Status: {payload.status}, Error: {payload.error_message}"
        )

    # Simple test command
    @commands.command(name="hi")
    async def hi_command(self, ctx: commands.Context):
        await ctx.reply(f"Hello, {ctx.author.name}! I can hear you!")

    # This will print every Twitch chat message to your terminal!
    @commands.Component.listener()
    async def event_message(self, payload: twitchio.ChatMessage) -> None:
        # Don't log the bot's own messages to avoid spam
        if payload.chatter.id == settings.TWITCH_BOT_ID:
            return
        log.info(f"[CHAT] {payload.chatter.name}: {payload.text}")

    @commands.command(name="lc")
    async def leetcode_command(self, ctx: commands.Context):
        """
        Usage: !lc https://leetcode.com/problems/two-sum/
        Logs the problem to the DB with a timestamp.
        """
        # Parse the message content to get the URL
        try:
            url = ctx.message.content.split(" ")[1]
        except IndexError:
            await ctx.reply(f"@{ctx.author.name} Usage: !lc [url]")
            return

        if "leetcode.com/problems/" not in url:
            await ctx.reply("Invalid LeetCode URL.")
            return

        # Extract slug and title
        try:
            slug = url.split("problems/")[1].split("/")[0]
            title = slug.replace("-", " ").title()
        except Exception:
            await ctx.reply("Could not parse problem slug.")
            return

        active_session = await self.get_active_session()

        if not active_session:
            await ctx.reply(
                "⚠️ No active stream session found in DB. (Is the Discord bot running?)"
            )
            return

        # Calculate timestamp relative to stream start
        # Ensure database timezone is handled correctly (usually stored as UTC)
        now = datetime.now(timezone.utc)

        # If start_time is naive, assume UTC (or handle based on your DB driver settings)
        start_time = active_session.start_time
        if start_time.tzinfo is None:
            start_time = start_time.replace(tzinfo=timezone.utc)

        delta = now - start_time
        hours, remainder = divmod(int(delta.total_seconds()), 3600)
        minutes, seconds = divmod(remainder, 60)
        timestamp_str = f"{hours:02}h{minutes:02}m{seconds:02}s"

        try:
            async with get_session() as session:
                event = StreamEvent(
                    session_id=active_session.id,
                    event_type="leetcode",
                    title=title,
                    url=url,
                    platform_id=slug,
                    vod_timestamp=timestamp_str,
                )
                session.add(event)
                await session.commit()

            await ctx.reply(f"✅ Logged: {title} @ {timestamp_str}")
            log.info(f"Logged LeetCode event: {title}")
        except Exception as e:
            log.error("DB Error logging LC event", exc_info=e)

    @commands.command(name="ad")
    async def run_ad(self, ctx: commands.Context):
        """
        Usage: !ad 1 (for 1 minute) or !ad 3 (for 3 minutes)
        """
        # Security: Only allow the broadcaster or mods to run ads
        if not ctx.author.is_broadcaster and not ctx.author.is_mod:
            return

        try:
            # Get the number of minutes requested (default to 3 if not specified)
            args = ctx.message.content.split(" ")
            minutes = int(args[1]) if len(args) > 1 else 3
        except ValueError:
            await ctx.reply("Usage: !ad [minutes]")
            return

        # Map simple minutes to Twitch's specific allowed seconds
        # 1 -> 60, 2 -> 120, 3 -> 180
        duration_seconds = minutes * 60

        # Validate against Twitch rules
        valid_seconds = [30, 60, 90, 120, 150, 180]
        if duration_seconds not in valid_seconds:
            # Pick the closest valid duration or default to 180
            duration_seconds = 180

        try:
            # twitchio command to trigger commercial
            # Note: channel.user is how we access the channel owner in twitchio
            # We assume ctx.channel is the channel object
            await ctx.channel.user.start_commercial(length=duration_seconds)
            await ctx.reply(f"🎬 Running {minutes}m ad break. Stretch! 🧘")
            log.info(f"Triggered {minutes}m ad break.")
        except Exception as e:
            log.error("Failed to run ad", exc_info=e)
            await ctx.reply(f"❌ Failed to run ad: {e}")


class TwitchBot(commands.AutoBot):
    def __init__(self):
        # We tell Twitch: "Send all chat messages from the Owner's channel to this Bot"
        chat_sub = eventsub.ChatMessageSubscription(
            broadcaster_user_id=settings.TWITCH_OWNER_ID, user_id=settings.TWITCH_BOT_ID
        )

        super().__init__(
            client_id=settings.TWITCH_CLIENT_ID,
            client_secret=settings.TWITCH_CLIENT_SECRET,
            bot_id=settings.TWITCH_BOT_ID,
            owner_id=settings.TWITCH_OWNER_ID,
            prefix="!",
            # AutoBot will automatically find and register the commands component
            components=["__main__.BotCommands"],
            subscriptions=[chat_sub],
        )

    # async def event_ready(self) -> None:
    #     log.info(f"Twitch AutoBot is ONLINE! (Bot ID: {self.bot_id})")
    #     log.info("Awaiting authorization... visit http://localhost:4343/oauth")

    async def event_ready(self) -> None:
        # Sanity check our IDs at startup
        log.info("-" * 40)
        log.info(f"Twitch AutoBot is ONLINE!")
        log.info(f"Using Owner/Streamer ID: {self.owner_id}")
        log.info(f"Using Bot ID:              {self.bot_id}")
        log.info("Attempting to subscribe to chat messages...")
        log.info("-" * 40)

    async def event_oauth_authorized(
        self, payload: twitchio.authentication.UserTokenPayload
    ) -> None:
        """Called when the bot successfully receives an OAuth token."""
        # We must explicitly add the token to the bot's internal manager
        await self.add_token(payload.access_token, payload.refresh_token)

        log.info(
            f"✅ Authorization successful for User ID: {payload.user_id}! Tokens saved."
        )


if __name__ == "__main__":
    bot = TwitchBot()
    bot.run()
