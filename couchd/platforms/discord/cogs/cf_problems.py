# couchd/platforms/discord/cogs/cf_problems.py
import logging
import discord
from discord.ext import commands, tasks
from sqlalchemy import select, func

from couchd.core.config import settings
from couchd.core.db import get_session
from couchd.core.models import GuildConfig, StreamEvent, CFProblemAttempt
from couchd.core.constants import CFProblemsConfig
from couchd.core.clients import codeforces as cf_client
from couchd.core.utils import get_active_session, compute_vod_timestamp
from couchd.platforms.discord.components.cf_problems_forum import sync_cf_problem

log = logging.getLogger(__name__)


class CFProblemsWatcherCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.last_processed_attempt_id: int = 0
        self.check_cf_problems.start()

    def cog_unload(self):
        self.check_cf_problems.cancel()

    @commands.Cog.listener()
    async def on_ready(self):
        await self._seed_watermark()

    async def _seed_watermark(self):
        async with get_session() as db:
            result = await db.execute(select(func.max(CFProblemAttempt.id)))
            max_id = result.scalar_one_or_none()
        self.last_processed_attempt_id = max_id or 0
        log.info(
            "CFProblemsWatcherCog watermark seeded at attempt_id=%d",
            self.last_processed_attempt_id,
        )

    @tasks.loop(minutes=CFProblemsConfig.POLL_RATE_MINUTES)
    async def check_cf_problems(self):
        await self.bot.wait_until_ready()

        async with get_session() as db:
            config = (
                await db.execute(
                    select(GuildConfig).where(GuildConfig.cf_problems_forum_id.isnot(None))
                )
            ).scalar_one_or_none()

        if settings.CODEFORCES_HANDLE:
            await self._poll_streamer_submissions()

        if not config:
            return

        forum = self.bot.get_channel(config.cf_problems_forum_id)
        if not isinstance(forum, discord.ForumChannel):
            return

        async with get_session() as db:
            new_attempts = (
                await db.execute(
                    select(CFProblemAttempt)
                    .join(StreamEvent)
                    .where(CFProblemAttempt.id > self.last_processed_attempt_id)
                    .order_by(CFProblemAttempt.id.asc())
                )
            ).scalars().all()

        if new_attempts:
            problem_ids = {a.problem_id for a in new_attempts}
            for pid in problem_ids:
                await sync_cf_problem(forum, pid, self.bot)
            self.last_processed_attempt_id = new_attempts[-1].id

    async def _poll_streamer_submissions(self):
        active_session = await get_active_session()
        if not active_session:
            return

        async with get_session() as db:
            current = (
                await db.execute(
                    select(CFProblemAttempt)
                    .join(StreamEvent)
                    .where(StreamEvent.session_id == active_session.id)
                    .order_by(StreamEvent.timestamp.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()

        if not current:
            return

        submissions = await cf_client.fetch_recent_ac_submissions(
            settings.CODEFORCES_HANDLE, count=10
        )
        matching = [
            s for s in submissions
            if s["contest_id"] == current.contest_id and s["index"] == current.index
        ]

        for sub in matching:
            sub_url = f"{cf_client._CF_BASE}/contest/{sub['contest_id']}/submission/{sub['submission_id']}"
            vod_ts = compute_vod_timestamp(active_session.start_time)
            async with get_session() as db:
                existing = (
                    await db.execute(
                        select(CFProblemAttempt).where(
                            CFProblemAttempt.id == current.id
                        )
                    )
                ).scalar_one_or_none()
                if existing and not existing.tags:
                    existing.tags = ", ".join(sub.get("tags", []))
                    await db.commit()
            log.info(
                "Auto-detected CF AC for %s%s (submission %s)",
                current.contest_id,
                current.index,
                sub["submission_id"],
            )


def setup(bot):
    bot.add_cog(CFProblemsWatcherCog(bot))
