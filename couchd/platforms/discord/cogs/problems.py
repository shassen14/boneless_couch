# couchd/platforms/discord/cogs/problems.py
import logging
import discord
from discord.ext import commands, tasks
from sqlalchemy import select, func

from couchd.core.config import settings
from couchd.core.db import get_session
from couchd.core.models import GuildConfig, ProblemPost, StreamEvent
from couchd.core.constants import BrandColors, LeetCodeConfig, ProblemsConfig
from couchd.core.clients.leetcode import LeetCodeClient
from couchd.platforms.twitch.components.utils import get_active_session, compute_vod_timestamp

log = logging.getLogger(__name__)


class ProblemsWatcherCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.lc_client = LeetCodeClient()
        self.last_processed_event_id: int = 0
        self.check_problems.start()

    def cog_unload(self):
        self.check_problems.cancel()

    @commands.Cog.listener()
    async def on_ready(self):
        await self._seed_watermark()

    async def _seed_watermark(self):
        async with get_session() as db:
            stmt = select(func.max(StreamEvent.id)).where(
                StreamEvent.event_type.in_(["leetcode", "solution"])
            )
            result = await db.execute(stmt)
            max_id = result.scalar_one_or_none()
        self.last_processed_event_id = max_id or 0
        log.info("ProblemsWatcherCog watermark seeded at event_id=%d", self.last_processed_event_id)

    @tasks.loop(minutes=ProblemsConfig.POLL_RATE_MINUTES)
    async def check_problems(self):
        await self.bot.wait_until_ready()

        async with get_session() as db:
            cfg_stmt = select(GuildConfig).where(GuildConfig.problems_forum_id.isnot(None))
            cfg_result = await db.execute(cfg_stmt)
            config = cfg_result.scalar_one_or_none()

        if not config:
            return

        forum = self.bot.get_channel(config.problems_forum_id)
        if not isinstance(forum, discord.ForumChannel):
            return

        async with get_session() as db:
            evt_stmt = (
                select(StreamEvent)
                .where(
                    StreamEvent.id > self.last_processed_event_id,
                    StreamEvent.event_type.in_(["leetcode", "solution"]),
                )
                .order_by(StreamEvent.id.asc())
            )
            evt_result = await db.execute(evt_stmt)
            new_events = evt_result.scalars().all()

        await self._poll_streamer_solutions()

        if not new_events:
            return

        slugs = {e.platform_id for e in new_events if e.platform_id}
        for slug in slugs:
            await self._sync_problem(forum, slug)

        self.last_processed_event_id = new_events[-1].id

    async def _poll_streamer_solutions(self):
        if not settings.LEETCODE_USERNAME:
            return

        active_session = await get_active_session()
        if not active_session:
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
            lc_event = result.scalar_one_or_none()

        if not lc_event:
            return

        submissions = await self.lc_client.fetch_recent_ac_submissions(settings.LEETCODE_USERNAME)
        matching = [s for s in submissions if s["titleSlug"] == lc_event.platform_id]

        for sub in matching:
            url = LeetCodeConfig.SUBMISSION_URL.format(sub["id"])
            async with get_session() as db:
                dup_stmt = select(StreamEvent).where(
                    StreamEvent.url == url,
                    StreamEvent.event_type == "solution",
                )
                dup_result = await db.execute(dup_stmt)
                if dup_result.scalar_one_or_none():
                    continue

                vod_ts = compute_vod_timestamp(active_session.start_time)
                db.add(StreamEvent(
                    session_id=active_session.id,
                    event_type="solution",
                    title=settings.TWITCH_CHANNEL,
                    url=url,
                    platform_id=lc_event.platform_id,
                    vod_timestamp=vod_ts,
                ))
                await db.commit()
            log.info("Auto-logged streamer solution for %s (submission %s)", lc_event.platform_id, sub["id"])

    async def _sync_problem(self, forum: discord.ForumChannel, slug: str):
        async with get_session() as db:
            stmt = select(ProblemPost).where(ProblemPost.platform_id == slug)
            result = await db.execute(stmt)
            post = result.scalar_one_or_none()

        if post:
            await self._update_thread(forum, slug, post)
        else:
            await self._create_thread(forum, slug)

    async def _build_embed(self, slug: str):
        async with get_session() as db:
            stmt = (
                select(StreamEvent)
                .where(
                    StreamEvent.platform_id == slug,
                    StreamEvent.event_type.in_(["leetcode", "solution"]),
                )
                .order_by(StreamEvent.timestamp.asc())
            )
            result = await db.execute(stmt)
            events = result.scalars().all()

        lc_events = [e for e in events if e.event_type == "leetcode"]
        solution_events = [e for e in events if e.event_type == "solution"]

        if not lc_events:
            return None, None, []

        first = lc_events[0]
        embed = discord.Embed(
            title=first.title,
            url=first.url,
            color=BrandColors.PRIMARY,
        )
        embed.add_field(name="Difficulty", value=first.status or "Unknown", inline=True)
        if first.rating:
            embed.add_field(name="Rating", value=str(first.rating), inline=True)

        appearances = "\n".join(
            f"Stream attempt · [{e.vod_timestamp}]({e.url})" for e in lc_events
        )
        embed.add_field(name=f"Appearances ({len(lc_events)})", value=appearances, inline=False)

        streamer_solutions = [
            e for e in solution_events
            if e.title.lower() == settings.TWITCH_CHANNEL.lower()
        ]
        community_solutions = [
            e for e in solution_events
            if e.title.lower() != settings.TWITCH_CHANNEL.lower()
        ]

        if streamer_solutions:
            lines = "\n".join(
                f"[Submission]({e.url}) · {e.vod_timestamp}" for e in streamer_solutions
            )
            embed.add_field(name="Streamer's Solutions", value=lines, inline=False)

        if community_solutions:
            lines = "\n".join(
                f"[{e.title}'s solution]({e.url}) · {e.vod_timestamp}" for e in community_solutions
            )
            embed.add_field(name="Community Solutions", value=lines, inline=False)

        if not solution_events:
            embed.add_field(name="Status", value="Attempted — no solution linked yet", inline=False)

        thread_name = first.title[: ProblemsConfig.TITLE_MAX_LEN]
        return thread_name, embed, lc_events

    def _resolve_tags(self, forum: discord.ForumChannel, difficulty: str | None):
        if not difficulty:
            return []
        return [t for t in forum.available_tags if t.name == difficulty]

    async def _create_thread(self, forum: discord.ForumChannel, slug: str):
        thread_name, embed, lc_events = await self._build_embed(slug)
        if not embed:
            return

        tags = self._resolve_tags(forum, lc_events[0].status if lc_events else None)
        try:
            thread = await forum.create_thread(
                name=thread_name,
                embed=embed,
                applied_tags=tags,
                auto_archive_duration=discord.ThreadArchiveDuration.week,
            )
            async with get_session() as db:
                db.add(ProblemPost(platform_id=slug, forum_thread_id=thread.id))
                await db.commit()
            log.info("Created forum thread for %s (thread_id=%d)", slug, thread.id)
        except Exception:
            log.error("Failed to create forum thread for %s", slug, exc_info=True)

    async def _update_thread(self, forum: discord.ForumChannel, slug: str, post: ProblemPost):
        thread_name, embed, lc_events = await self._build_embed(slug)
        if not embed:
            return

        tags = self._resolve_tags(forum, lc_events[0].status if lc_events else None)
        try:
            thread = forum.get_thread(post.forum_thread_id)
            if not thread:
                thread = await self.bot.fetch_channel(post.forum_thread_id)

            if thread.archived:
                await thread.edit(archived=False)

            starter_msg = await thread.fetch_message(thread.id)
            await starter_msg.edit(embed=embed)
            await thread.edit(applied_tags=tags, name=thread_name)
            log.info("Updated forum thread for %s", slug)
        except Exception:
            log.error("Failed to update forum thread for %s", slug, exc_info=True)


def setup(bot):
    bot.add_cog(ProblemsWatcherCog(bot))
