# couchd/platforms/twitch/commands.py
import logging
import twitchio
from twitchio.ext import commands
from sqlalchemy import select

from couchd.core.config import settings
from couchd.core.db import get_session
from couchd.core.models import StreamEvent
from couchd.platforms.twitch.leetcode_client import LeetCodeClient
from couchd.platforms.twitch.ad_manager import AdBudgetManager
from couchd.platforms.twitch.metrics_tracker import ChatVelocityTracker
from couchd.platforms.twitch.github_client import GitHubClient
from couchd.platforms.twitch.utils import get_active_session, compute_vod_timestamp, clamp_to_ad_duration

log = logging.getLogger(__name__)


class BotCommands(commands.Component):
    """Holds all chat commands for the bot."""

    def __init__(
        self,
        bot: commands.Bot,
        lc_client: LeetCodeClient,
        ad_manager: AdBudgetManager,
        metrics_tracker: ChatVelocityTracker,
        github_client: GitHubClient,
    ):
        self.bot = bot
        self.lc_client = lc_client
        self.ad_manager = ad_manager
        self.metrics_tracker = metrics_tracker
        self.github_client = github_client

    @commands.Component.listener()
    async def event_message(self, payload: twitchio.ChatMessage) -> None:
        if payload.chatter.id == settings.TWITCH_BOT_ID:
            return
        log.info(f"[CHAT] {payload.chatter.name}: {payload.text}")
        self.metrics_tracker.record_message()

    # ------------------------------------------------------------------
    # !hi
    # ------------------------------------------------------------------

    @commands.command(name="hi")
    async def hi_command(self, ctx: commands.Context):
        await ctx.reply(f"Hello, {ctx.chatter.name}! I can hear you!")

    # ------------------------------------------------------------------
    # !lc
    # ------------------------------------------------------------------

    @commands.command(name="lc")
    async def leetcode_command(self, ctx: commands.Context):
        """
        !lc          — show the current LeetCode problem (anyone)
        !lc <url>    — log a new problem (broadcaster/mod only)
        """
        args = ctx.content.split()

        # ---- Bare !lc: show current problem ----
        if len(args) < 2:
            active_session = await get_active_session()
            if not active_session:
                await ctx.reply("⚠️ No active stream session.")
                return

            async with get_session() as db:
                stmt = (
                    select(StreamEvent)
                    .where(
                        StreamEvent.session_id == active_session.id,
                        StreamEvent.event_type == "leetcode",
                    )
                    .order_by(StreamEvent.timestamp.desc())
                    .limit(1)
                )
                result = await db.execute(stmt)
                event = result.scalar_one_or_none()

            if not event:
                await ctx.reply("No LeetCode problem logged yet.")
            else:
                await ctx.reply(event.url)
            return

        # ---- !lc <url>: log new problem ----
        if not ctx.author.broadcaster and not ctx.author.moderator:
            return

        url = args[1]
        if "leetcode.com/problems/" not in url:
            await ctx.reply("Invalid LeetCode URL.")
            return

        try:
            slug = url.split("problems/")[1].split("/")[0]
        except Exception:
            await ctx.reply("Could not parse problem slug.")
            return

        active_session = await get_active_session()
        if not active_session:
            await ctx.reply(
                "⚠️ No active stream session found in DB. (Is the Discord bot running?)"
            )
            return

        data = await self.lc_client.fetch_problem(slug)
        if not data:
            await ctx.reply("❌ Could not fetch problem data from LeetCode.")
            return

        rating = self.lc_client.get_rating(data["id"])
        rating_int = round(rating) if rating is not None else None
        title_str = f"{data['id']}. {data['title']}"
        vod_ts = compute_vod_timestamp(active_session.start_time)

        try:
            async with get_session() as db:
                event = StreamEvent(
                    session_id=active_session.id,
                    event_type="leetcode",
                    title=title_str,
                    url=url,
                    platform_id=slug,
                    status=data["difficulty"],
                    rating=rating_int,
                    vod_timestamp=vod_ts,
                )
                db.add(event)
                await db.commit()

            if rating_int is not None:
                reply = f"✅ {title_str} | {data['difficulty']} | Rating: {rating_int} @ {vod_ts}"
            else:
                reply = f"✅ {title_str} | {data['difficulty']} @ {vod_ts}"
            await ctx.reply(reply)
            log.info("Logged LeetCode event: %s", title_str)
        except Exception:
            log.error("DB error logging LC event", exc_info=True)
            await ctx.reply("❌ Failed to save to DB.")

    # ------------------------------------------------------------------
    # !project
    # ------------------------------------------------------------------

    @commands.command(name="project")
    async def project_command(self, ctx: commands.Context):
        """
        !project          — show the current project (anyone)
        !project <url>    — set the active GitHub project (broadcaster/mod only)
        """
        args = ctx.content.split()

        # ---- Bare !project: show current ----
        if len(args) < 2:
            active_session = await get_active_session()
            if not active_session:
                await ctx.reply("⚠️ No active stream session.")
                return

            async with get_session() as db:
                stmt = (
                    select(StreamEvent)
                    .where(
                        StreamEvent.session_id == active_session.id,
                        StreamEvent.event_type == "project",
                    )
                    .order_by(StreamEvent.timestamp.desc())
                    .limit(1)
                )
                result = await db.execute(stmt)
                event = result.scalar_one_or_none()

            if not event:
                await ctx.reply("No project logged yet.")
            else:
                if event.status:
                    await ctx.reply(f"Now working on: {event.title} — {event.status}")
                else:
                    await ctx.reply(f"Now working on: {event.title}")
            return

        # ---- !project <url>: set project ----
        if not ctx.author.broadcaster and not ctx.author.moderator:
            return

        url = args[1]
        try:
            path = url.rstrip("/").split("github.com/")[1]
            parts = path.split("/")
            owner, repo = parts[0], parts[1]
        except (IndexError, ValueError):
            await ctx.reply("Invalid GitHub URL.")
            return

        active_session = await get_active_session()
        if not active_session:
            await ctx.reply("⚠️ No active stream session found in DB.")
            return

        description = await self.github_client.fetch_repo(owner, repo)
        repo_name = f"{owner}/{repo}"

        try:
            async with get_session() as db:
                event = StreamEvent(
                    session_id=active_session.id,
                    event_type="project",
                    title=repo_name,
                    url=url,
                    status=description,
                )
                db.add(event)
                await db.commit()

            if description:
                await ctx.reply(f"Now working on: {repo_name} — {description}")
            else:
                await ctx.reply(f"Now working on: {repo_name}")
            log.info("Logged project event: %s", repo_name)
        except Exception:
            log.error("DB error logging project event", exc_info=True)
            await ctx.reply("❌ Failed to save to DB.")

    # ------------------------------------------------------------------
    # !ad
    # ------------------------------------------------------------------

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
        if len(args) > 1:
            try:
                minutes = int(args[1])
            except ValueError:
                await ctx.reply("Usage: !ad [minutes]")
                return
            duration_seconds = clamp_to_ad_duration(minutes * 60)
        else:
            remaining = await self.ad_manager.get_remaining(active_session.id)
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

        minutes_run = duration_seconds // 60
        await ctx.reply(f"🎬 Running {minutes_run}m ad. Time to stretch!")
        log.info("Triggered %ds ad break.", duration_seconds)
