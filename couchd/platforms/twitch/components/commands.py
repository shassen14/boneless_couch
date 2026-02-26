# couchd/platforms/twitch/components/commands.py
import asyncio
import logging
import re
from datetime import datetime, timezone, timedelta
import twitchio
from twitchio.ext import commands
from sqlalchemy import select

from couchd.core.config import settings
from couchd.core.db import get_session
from couchd.core.models import StreamEvent
from couchd.core.clients.youtube import YouTubeRSSClient
from couchd.core.clients.leetcode import LeetCodeClient
from couchd.core.clients.github import GitHubClient
from couchd.core.constants import CommandCooldowns
from couchd.platforms.twitch.ads.manager import AdBudgetManager
from couchd.platforms.twitch.ads.messages import pick_ad_message, pick_return_message
from couchd.platforms.twitch.components.metrics_tracker import ChatVelocityTracker
from couchd.platforms.twitch.components.cooldowns import CooldownManager
from couchd.platforms.twitch.components.utils import get_active_session, compute_vod_timestamp, clamp_to_ad_duration, send_chat_message

log = logging.getLogger(__name__)

_LC_SUBMISSION_SLUG = re.compile(r'leetcode\.com/problems/([\w-]+)/submissions/\d+')
_LC_SUBMISSION_BARE = re.compile(r'leetcode\.com/submissions/detail/\d+')
_URL_RE = re.compile(r'https?://\S+')


class BotCommands(commands.Component):
    """Holds all chat commands for the bot."""

    def __init__(
        self,
        bot: commands.Bot,
        lc_client: LeetCodeClient,
        ad_manager: AdBudgetManager,
        metrics_tracker: ChatVelocityTracker,
        github_client: GitHubClient,
        youtube_client: YouTubeRSSClient | None,
    ):
        self.bot = bot
        self.lc_client = lc_client
        self.ad_manager = ad_manager
        self.metrics_tracker = metrics_tracker
        self.github_client = github_client
        self.youtube_client = youtube_client
        self.cooldowns = CooldownManager()

    @commands.Component.listener()
    async def event_message(self, payload: twitchio.ChatMessage) -> None:
        if payload.chatter.id == settings.TWITCH_BOT_ID:
            return
        log.info(f"[CHAT] {payload.chatter.name}: {payload.text}")
        self.metrics_tracker.record_message()
        await self._check_solution_url(payload)

    async def _check_solution_url(self, payload: twitchio.ChatMessage) -> None:
        slug_match = _LC_SUBMISSION_SLUG.search(payload.text)
        if slug_match:
            slug = slug_match.group(1)
        elif _LC_SUBMISSION_BARE.search(payload.text):
            slug = None
        else:
            return

        url_match = _URL_RE.search(payload.text)
        if not url_match:
            return
        url = url_match.group(0)

        active_session = await get_active_session()
        if not active_session:
            return

        async with get_session() as db:
            lc_stmt = (
                select(StreamEvent)
                .where(
                    StreamEvent.session_id == active_session.id,
                    StreamEvent.event_type == "leetcode",
                )
                .order_by(StreamEvent.timestamp.desc())
                .limit(1)
            )
            lc_result = await db.execute(lc_stmt)
            lc_event = lc_result.scalar_one_or_none()

            if not lc_event:
                return
            if slug and slug != lc_event.platform_id:
                return

            dup_stmt = select(StreamEvent).where(
                StreamEvent.url == url,
                StreamEvent.event_type == "solution",
            )
            dup_result = await db.execute(dup_stmt)
            if dup_result.scalar_one_or_none():
                return

            vod_ts = compute_vod_timestamp(active_session.start_time)
            db.add(StreamEvent(
                session_id=active_session.id,
                event_type="solution",
                title=payload.chatter.name,
                url=url,
                platform_id=lc_event.platform_id,
                vod_timestamp=vod_ts,
            ))
            await db.commit()

        log.info("Logged solution from %s for %s", payload.chatter.name, lc_event.platform_id)

    # ------------------------------------------------------------------
    # !commands
    # ------------------------------------------------------------------

    @commands.command(name="commands")
    async def commands_list(self, ctx: commands.Context):
        """!commands — list all available bot commands."""
        if self.cooldowns.check("commands", ctx.author.id, CommandCooldowns.COMMANDS):
            return
        self.cooldowns.record("commands", ctx.author.id)

        public = "Commands: !lc (current problem) · !project (current project)"
        if self.youtube_client:
            public += " · !newvideo (latest YouTube video)"

        await ctx.reply(public)

    # ------------------------------------------------------------------
    # !newvideo
    # ------------------------------------------------------------------

    @commands.command(name="newvideo")
    async def newvideo_command(self, ctx: commands.Context):
        """!newvideo — show the title and link of the latest YouTube video."""
        if self.cooldowns.check("newvideo", ctx.author.id, CommandCooldowns.NEWVIDEO):
            return
        self.cooldowns.record("newvideo", ctx.author.id)

        if not self.youtube_client:
            await ctx.reply("YouTube is not configured.")
            return

        video = await self.youtube_client.get_latest_video()
        if not video:
            await ctx.reply("Could not fetch the latest video right now.")
            return

        await ctx.reply(f"{video['title']} → {video['video_url']}")

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
            if self.cooldowns.check("lc", ctx.author.id, CommandCooldowns.LC):
                return
            self.cooldowns.record("lc", ctx.author.id)

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
            if self.cooldowns.check("project", ctx.author.id, CommandCooldowns.PROJECT):
                return
            self.cooldowns.record("project", ctx.author.id)

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
        end_time = ends_at.strftime("%-I:%M:%S %p UTC")

        whole_minutes, leftover_seconds = divmod(duration_seconds, 60)
        duration_label = f"{whole_minutes}m {leftover_seconds}s" if leftover_seconds else f"{whole_minutes}m"
        await ctx.reply(f"🎬 Running {duration_label} ad — ends ~{end_time}. Time to stretch!")
        log.info("Triggered %ds ad break.", duration_seconds)

        latest_video = await self.youtube_client.get_latest_video() if self.youtube_client else None
        ad_msg = pick_ad_message(latest_video)
        if ad_msg:
            await send_chat_message(self.bot, ad_msg)

        async def _notify_return() -> None:
            await asyncio.sleep(duration_seconds)
            await send_chat_message(self.bot, pick_return_message())

        asyncio.create_task(_notify_return())
