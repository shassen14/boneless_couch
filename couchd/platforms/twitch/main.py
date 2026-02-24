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
from couchd.core.constants import Platform

# Initialize centralized logging
setup_logging()
log = logging.getLogger(__name__)


class BotCommands(commands.Component):
    """Holds all the chat commands for the bot."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def get_active_session(self):
        """Helper to find the active StreamSession in our DB."""
        async with get_session() as session:
            stmt = select(StreamSession).where(
                (StreamSession.is_active == True)
                & (StreamSession.platform == Platform.TWITCH.value)
            )
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    @commands.Component.listener()
    async def event_message(self, payload: twitchio.ChatMessage) -> None:
        if payload.chatter.id == settings.TWITCH_BOT_ID:
            return
        log.info(f"[CHAT] {payload.chatter.name}: {payload.text}")

    @commands.command(name="hi")
    async def hi_command(self, ctx: commands.Context):
        await ctx.reply(f"Hello, {ctx.chatter.name}! I can hear you!")

    @commands.command(name="lc")
    async def leetcode_command(self, ctx: commands.Context):
        """
        Usage: !lc https://leetcode.com/problems/two-sum/
        Logs the problem to the DB with a timestamp.
        """
        try:
            url = ctx.content.split(" ")[1]
        except IndexError:
            await ctx.reply(f"@{ctx.chatter.name} Usage: !lc [url]")
            return

        if "leetcode.com/problems/" not in url:
            await ctx.reply("Invalid LeetCode URL.")
            return

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

        now = datetime.now(timezone.utc)
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
        if not ctx.author.broadcaster and not ctx.author.moderator:
            return

        try:
            args = ctx.content.split(" ")
            minutes = int(args[1]) if len(args) > 1 else 3
        except ValueError:
            await ctx.reply("Usage: !ad [minutes]")
            return

        duration_seconds = minutes * 60
        valid_seconds = [30, 60, 90, 120, 150, 180]
        if duration_seconds not in valid_seconds:
            duration_seconds = 180

        try:
            await ctx.channel.start_commercial(length=duration_seconds)
            await ctx.reply(f"🎬 Running {minutes}m ad break. Stretch! 🧘")
            log.info(f"Triggered {minutes}m ad break.")
        except Exception as e:
            log.error("Failed to run ad", exc_info=e)
            await ctx.reply(f"❌ Failed to run ad: {e}")


class TwitchBot(commands.Bot):
    def __init__(self):
        super().__init__(
            client_id=settings.TWITCH_CLIENT_ID,
            client_secret=settings.TWITCH_CLIENT_SECRET,
            bot_id=settings.TWITCH_BOT_ID,
            owner_id=settings.TWITCH_OWNER_ID,
            prefix="!",
        )

    async def setup_hook(self) -> None:
        await self.add_component(BotCommands(self))

        # Subscribe to chat on startup (works on subsequent runs once a token is saved).
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


if __name__ == "__main__":
    bot = TwitchBot()
    bot.run()
