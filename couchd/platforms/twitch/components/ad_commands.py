# couchd/platforms/twitch/components/ad_commands.py
import asyncio
import logging
from datetime import datetime, timezone, timedelta
from twitchio.ext import commands

from couchd.core.clients.youtube import YouTubeRSSClient
from couchd.platforms.twitch.ads.manager import AdBudgetManager
from couchd.platforms.twitch.ads.messages import pick_ad_message, pick_return_message
from couchd.platforms.twitch.components.utils import clamp_to_ad_duration, send_chat_message
from couchd.core.utils import get_active_session, compute_vod_timestamp

log = logging.getLogger(__name__)


class AdCommands(commands.Component):
    def __init__(
        self,
        bot: commands.Bot,
        ad_manager: AdBudgetManager,
        youtube_client: YouTubeRSSClient | None,
    ):
        self.bot = bot
        self.ad_manager = ad_manager
        self.youtube_client = youtube_client

    @commands.command(name="ad")
    async def run_ad(self, ctx: commands.Context):
        """
        !ad           — run the remaining ad budget for this window
        !ad <minutes> — run a specific duration ad
        """
        if not ctx.author.broadcaster and not ctx.author.moderator:
            return

        active_session = await get_active_session()
        if not active_session:
            await ctx.reply("⚠️ No active stream session.")
            return

        args = ctx.content.split()
        remaining = await self.ad_manager.get_remaining(active_session.id)
        if len(args) > 1:
            try:
                minutes = float(args[1])
            except ValueError:
                await ctx.reply("Usage: !ad [minutes] — e.g. !ad 1.5 for 90s")
                return
            requested = round(minutes * 60)
            if remaining == 0:
                await ctx.reply("Ad quota already met this hour.")
                return
            duration_seconds = clamp_to_ad_duration(min(requested, remaining))
        else:
            if remaining == 0:
                await ctx.reply("Ad quota already met this hour.")
                return
            duration_seconds = clamp_to_ad_duration(remaining)

        try:
            await ctx.channel.start_commercial(length=duration_seconds)
        except Exception as e:
            log.error("Failed to run ad", exc_info=True)
            await ctx.reply(f"❌ Failed to run ad: {e}")
            return

        vod_ts = compute_vod_timestamp(active_session.start_time)
        await self.ad_manager.log_ad(active_session.id, duration_seconds, vod_ts)
        self.ad_manager.cancel_pending()

        ends_at = datetime.now(timezone.utc) + timedelta(seconds=duration_seconds)
        return_time = ends_at.astimezone().strftime("%-I:%M %p")
        end_time = ends_at.strftime("%-I:%M:%S %p UTC")

        whole_minutes, leftover_seconds = divmod(duration_seconds, 60)
        duration_label = (
            f"{whole_minutes}m {leftover_seconds}s"
            if leftover_seconds
            else f"{whole_minutes}m"
        )
        await ctx.reply(
            f"🎬 Running {duration_label} ad — ends ~{end_time}. Time to stretch!"
        )
        log.info("Triggered %ds ad break.", duration_seconds)

        latest_video = (
            await self.youtube_client.get_latest_video()
            if self.youtube_client
            else None
        )
        ad_msg = pick_ad_message(latest_video, return_time)
        if ad_msg:
            await send_chat_message(self.bot, ad_msg)

        async def _notify_return() -> None:
            await asyncio.sleep(duration_seconds)
            await send_chat_message(self.bot, pick_return_message())

        asyncio.create_task(_notify_return())
