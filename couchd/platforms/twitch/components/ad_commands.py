# couchd/platforms/twitch/components/ad_commands.py
import asyncio
import logging
from datetime import datetime, timezone, timedelta
from http import HTTPStatus
from twitchio.exceptions import HTTPException
from twitchio.ext import commands

from couchd.core.clients.youtube import YouTubeRSSClient
from couchd.platforms.twitch.ads.manager import AdBudgetManager
from couchd.platforms.twitch.ads.messages import pick_ad_message, pick_return_message
from couchd.platforms.twitch.components.utils import clamp_to_ad_duration, send_chat_message
from couchd.core.utils import get_active_session, compute_vod_timestamp
from couchd.core.constants import AdReplies

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
        self._return_tasks: set[asyncio.Task] = set()

    def _parse_duration(self, content: str, remaining: int) -> int | None:
        """Seconds to run, clamped to remaining budget; None if the arg is invalid."""
        args = content.split()
        if len(args) <= 1:
            return clamp_to_ad_duration(remaining)
        try:
            requested = round(float(args[1]) * 60)
        except ValueError:
            return None
        if requested <= 0:
            return None
        return clamp_to_ad_duration(min(requested, remaining))

    async def _fail(self, ctx: commands.Context) -> None:
        """Release the reservation and report a generic failure."""
        self.ad_manager.release_fire()
        log.error("Failed to run ad", exc_info=True)
        await ctx.reply(AdReplies.FAILED)

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
            await ctx.reply(AdReplies.NO_ACTIVE_SESSION)
            return

        remaining = await self.ad_manager.get_remaining(active_session.id, active_session.start_time)
        if remaining == 0:
            await ctx.reply(AdReplies.QUOTA_MET)
            return

        duration_seconds = self._parse_duration(ctx.content, remaining)
        if duration_seconds is None:
            await ctx.reply(AdReplies.USAGE)
            return

        # Cancel any scheduled auto-ad and claim the fire slot before calling Twitch
        # so the manual ad and the scheduler can't both fire and trip a 429.
        self.ad_manager.cancel_pending()
        if not self.ad_manager.try_reserve_fire():
            await ctx.reply(AdReplies.JUST_RAN)
            return

        try:
            await ctx.channel.start_commercial(length=duration_seconds)
        except HTTPException as e:
            # The commercial never started, so free the reservation for a retry.
            if e.status == HTTPStatus.TOO_MANY_REQUESTS:
                self.ad_manager.release_fire()
                retry_after = e.extra.get("retry_after") if isinstance(e.extra, dict) else None
                wait = AdReplies.COOLDOWN_RETRY.format(minutes=round(retry_after / 60)) if retry_after else ""
                log.info("Ad on Twitch cooldown (retry_after=%s).", retry_after)
                await ctx.reply(AdReplies.COOLDOWN.format(wait=wait))
                return
            await self._fail(ctx)
            return
        except Exception:
            await self._fail(ctx)
            return

        vod_ts = compute_vod_timestamp(active_session.start_time)
        await self.ad_manager.log_ad(active_session.id, duration_seconds, vod_ts)

        ends_at = datetime.now(timezone.utc) + timedelta(seconds=duration_seconds)
        return_time = ends_at.astimezone().strftime("%-I:%M %p")
        await ctx.reply(AdReplies.BREAK.format(return_time=return_time))
        log.info("Triggered %ds ad break.", duration_seconds)

        latest_video = (
            await self.youtube_client.get_latest_video()
            if self.youtube_client
            else None
        )
        ad_msg = pick_ad_message(latest_video)
        if ad_msg:
            await send_chat_message(self.bot, ad_msg)

        async def _notify_return() -> None:
            await asyncio.sleep(duration_seconds)
            await send_chat_message(self.bot, pick_return_message())

        task = asyncio.create_task(_notify_return())
        self._return_tasks.add(task)
        task.add_done_callback(self._return_tasks.discard)
