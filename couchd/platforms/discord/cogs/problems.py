# couchd/platforms/discord/cogs/problems.py
import logging
import discord
from discord.ext import commands, tasks
from sqlalchemy import select, func

from couchd.core.config import settings
from couchd.core.db import get_session
from couchd.core.models import (
    GuildConfig,
    ProblemPost,
    StreamEvent,
    ProblemAttempt,
    SolutionPost,
)
from couchd.core.constants import BrandColors, LeetCodeConfig, ProblemsConfig
from couchd.core.clients.leetcode import LeetCodeClient
from couchd.platforms.twitch.components.utils import (
    get_active_session,
    compute_vod_timestamp,
)

log = logging.getLogger(__name__)


class ProblemsWatcherCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.lc_client = LeetCodeClient()
        self.last_processed_attempt_id: int = 0
        self.check_problems.start()

    def cog_unload(self):
        self.check_problems.cancel()

    @commands.Cog.listener()
    async def on_ready(self):
        await self._seed_watermark()

    async def _seed_watermark(self):
        async with get_session() as db:
            result = await db.execute(select(func.max(ProblemAttempt.id)))
            max_id = result.scalar_one_or_none()
        self.last_processed_attempt_id = max_id or 0
        log.info(
            "ProblemsWatcherCog watermark seeded at attempt_id=%d",
            self.last_processed_attempt_id,
        )

    @tasks.loop(minutes=ProblemsConfig.POLL_RATE_MINUTES)
    async def check_problems(self):
        await self.bot.wait_until_ready()

        async with get_session() as db:
            cfg_result = await db.execute(
                select(GuildConfig).where(GuildConfig.problems_forum_id.isnot(None))
            )
            config = cfg_result.scalar_one_or_none()

        await self._poll_streamer_solutions()

        if not config:
            return

        forum = self.bot.get_channel(config.problems_forum_id)
        if not isinstance(forum, discord.ForumChannel):
            return

        async with get_session() as db:
            new_attempts = (
                (
                    await db.execute(
                        select(ProblemAttempt)
                        .join(StreamEvent)
                        .where(ProblemAttempt.id > self.last_processed_attempt_id)
                        .order_by(ProblemAttempt.id.asc())
                    )
                )
                .scalars()
                .all()
            )

        if new_attempts:
            slugs = {a.slug for a in new_attempts}
            for slug in slugs:
                await self._sync_problem(forum, slug)
            self.last_processed_attempt_id = new_attempts[-1].id

        await self._flush_pending_solutions(forum)

    async def _poll_streamer_solutions(self):
        if not settings.LEETCODE_USERNAME:
            return

        active_session = await get_active_session()
        if not active_session:
            return

        async with get_session() as db:
            attempt = (
                await db.execute(
                    select(ProblemAttempt)
                    .join(StreamEvent)
                    .where(StreamEvent.session_id == active_session.id)
                    .order_by(StreamEvent.timestamp.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()

        if not attempt:
            return

        submissions = await self.lc_client.fetch_recent_ac_submissions(
            settings.LEETCODE_USERNAME
        )
        matching = [s for s in submissions if s["titleSlug"] == attempt.slug]

        for sub in matching:
            url = LeetCodeConfig.SUBMISSION_URL.format(sub["id"])
            vod_ts = compute_vod_timestamp(active_session.start_time)
            async with get_session() as db:
                sol = (
                    await db.execute(
                        select(SolutionPost).where(
                            SolutionPost.problem_slug == attempt.slug,
                            SolutionPost.platform == "twitch",
                            SolutionPost.username == settings.TWITCH_CHANNEL,
                        )
                    )
                ).scalar_one_or_none()
                if sol:
                    sol.url = url
                    sol.vod_timestamp = vod_ts
                else:
                    db.add(
                        SolutionPost(
                            problem_slug=attempt.slug,
                            platform="twitch",
                            username=settings.TWITCH_CHANNEL,
                            url=url,
                            vod_timestamp=vod_ts,
                        )
                    )
                await db.commit()
            log.info(
                "Auto-logged streamer solution for %s (submission %s)",
                attempt.slug,
                sub["id"],
            )

    async def _flush_pending_solutions(self, forum: discord.ForumChannel):
        async with get_session() as db:
            slugs = (
                (
                    await db.execute(
                        select(SolutionPost.problem_slug)
                        .distinct()
                        .where(SolutionPost.discord_message_id.is_(None))
                    )
                )
                .scalars()
                .all()
            )

        for slug in slugs:
            async with get_session() as db:
                post = (
                    await db.execute(
                        select(ProblemPost).where(ProblemPost.platform_id == slug)
                    )
                ).scalar_one_or_none()
            if not post:
                continue
            thread = forum.get_thread(post.forum_thread_id)
            if not thread:
                try:
                    thread = await self.bot.fetch_channel(post.forum_thread_id)
                except Exception:
                    log.warning("Could not fetch thread for slug %s", slug)
                    continue
            await self._sync_solution_comments(thread, slug)

    async def _sync_problem(self, forum: discord.ForumChannel, slug: str):
        async with get_session() as db:
            post = (
                await db.execute(
                    select(ProblemPost).where(ProblemPost.platform_id == slug)
                )
            ).scalar_one_or_none()

        if post:
            thread = await self._update_thread(forum, slug, post)
        else:
            thread, post = await self._create_thread(forum, slug)

        if thread and post:
            await self._sync_solution_comments(thread, slug)

    async def _build_embed(self, slug: str):
        async with get_session() as db:
            attempts = (
                (
                    await db.execute(
                        select(ProblemAttempt)
                        .join(StreamEvent)
                        .where(ProblemAttempt.slug == slug)
                        .order_by(StreamEvent.timestamp.asc())
                    )
                )
                .scalars()
                .all()
            )

        if not attempts:
            return None, None, []

        first = attempts[0]
        embed = discord.Embed(
            title=first.title,
            url=first.url,
            color=BrandColors.PRIMARY,
        )
        embed.add_field(
            name="Difficulty", value=first.difficulty or "Unknown", inline=True
        )
        if first.rating:
            embed.add_field(name="Rating", value=str(first.rating), inline=True)

        appearances = "\n".join(
            f"Stream attempt · [{a.vod_timestamp}]({a.url})" for a in attempts
        )
        embed.add_field(
            name=f"Appearances ({len(attempts)})", value=appearances, inline=False
        )

        async with get_session() as db:
            sol_count = (
                await db.execute(
                    select(func.count()).where(SolutionPost.problem_slug == slug)
                )
            ).scalar_one()

        if sol_count == 0:
            embed.add_field(
                name="Status", value="Attempted — no solution linked yet", inline=False
            )

        thread_name = first.title[: ProblemsConfig.TITLE_MAX_LEN]
        return thread_name, embed, attempts

    def _resolve_tags(self, forum: discord.ForumChannel, difficulty: str | None):
        if not difficulty:
            return []
        return [t for t in forum.available_tags if t.name == difficulty]

    async def _create_thread(self, forum: discord.ForumChannel, slug: str):
        thread_name, embed, attempts = await self._build_embed(slug)
        if not embed:
            return None, None

        tags = self._resolve_tags(forum, attempts[0].difficulty if attempts else None)
        try:
            thread = await forum.create_thread(
                name=thread_name,
                embed=embed,
                applied_tags=tags,
                auto_archive_duration=discord.ThreadArchiveDuration.one_week,
            )
            async with get_session() as db:
                post = ProblemPost(platform_id=slug, forum_thread_id=thread.id)
                db.add(post)
                await db.commit()
                await db.refresh(post)
            log.info("Created forum thread for %s (thread_id=%d)", slug, thread.id)
            return thread, post
        except Exception:
            log.error("Failed to create forum thread for %s", slug, exc_info=True)
            return None, None

    async def _update_thread(
        self, forum: discord.ForumChannel, slug: str, post: ProblemPost
    ):
        thread_name, embed, attempts = await self._build_embed(slug)
        if not embed:
            return None

        tags = self._resolve_tags(forum, attempts[0].difficulty if attempts else None)
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
            return thread
        except Exception:
            log.error("Failed to update forum thread for %s", slug, exc_info=True)
            return None

    async def _sync_solution_comments(self, thread: discord.Thread, slug: str):
        async with get_session() as db:
            rows = (
                (
                    await db.execute(
                        select(SolutionPost).where(SolutionPost.problem_slug == slug)
                    )
                )
                .scalars()
                .all()
            )

        for sol in rows:
            content = (
                f"**{sol.username}** solved this (via {sol.platform})!\n"
                f"[View Submission]({sol.url})"
            )
            if sol.discord_message_id:
                try:
                    msg = await thread.fetch_message(sol.discord_message_id)
                    await msg.edit(content=content)
                    continue
                except discord.NotFound:
                    pass  # message deleted — fall through to post new

            msg = await thread.send(content)
            async with get_session() as db:
                row = await db.get(SolutionPost, sol.id)
                row.discord_message_id = msg.id
                await db.commit()


def setup(bot):
    bot.add_cog(ProblemsWatcherCog(bot))
