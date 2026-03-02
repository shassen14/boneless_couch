# couchd/platforms/discord/cogs/problems.py
import logging
import discord
from discord.ext import commands, tasks
from sqlalchemy import select, func

from couchd.core.config import settings
from couchd.core.db import get_session
from couchd.core.models import GuildConfig, StreamEvent, ProblemAttempt, SolutionPost
from couchd.core.constants import LeetCodeConfig, ProblemsConfig
from couchd.core.clients.leetcode import LeetCodeClient
from couchd.core.utils import get_active_session, compute_vod_timestamp
from couchd.platforms.discord.components.problems_forum import (
    sync_problem,
    flush_pending_solutions,
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
                await sync_problem(forum, slug, self.bot)
            self.last_processed_attempt_id = new_attempts[-1].id

        await flush_pending_solutions(forum, self.bot)

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


def setup(bot):
    bot.add_cog(ProblemsWatcherCog(bot))
