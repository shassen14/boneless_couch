# couchd/platforms/twitch/components/lc_commands.py
import logging
import re
import twitchio
from twitchio.ext import commands
from sqlalchemy import select

from couchd.core.config import settings
from couchd.core.db import get_session
from couchd.core.models import StreamEvent, ProblemAttempt, SolutionPost, ProblemPost
from couchd.core.clients.leetcode import LeetCodeClient
from couchd.core.constants import CommandCooldowns
from couchd.platforms.twitch.components.metrics_tracker import ChatVelocityTracker
from couchd.platforms.twitch.components.cooldowns import CooldownManager
from couchd.core.utils import get_active_session, compute_vod_timestamp

log = logging.getLogger(__name__)

_LC_SUBMISSION_SLUG = re.compile(r"leetcode\.com/problems/([\w-]+)/submissions/\d+")
_LC_SUBMISSION_BARE = re.compile(r"leetcode\.com/submissions/detail/\d+")
_URL_RE = re.compile(r"https?://\S+")


class LCCommands(commands.Component):
    def __init__(self, lc_client: LeetCodeClient, metrics_tracker: ChatVelocityTracker):
        self.lc_client = lc_client
        self.metrics_tracker = metrics_tracker
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

        async with get_session() as db:
            if slug:
                post = (
                    await db.execute(
                        select(ProblemPost).where(ProblemPost.platform_id == slug)
                    )
                ).scalar_one_or_none()
                if not post:
                    return
            else:
                if not active_session:
                    return
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
                slug = attempt.slug

            username = payload.chatter.name
            vod_ts = (
                compute_vod_timestamp(active_session.start_time)
                if active_session
                else None
            )
            sol = (
                await db.execute(
                    select(SolutionPost).where(
                        SolutionPost.problem_slug == slug,
                        SolutionPost.platform == "twitch",
                        SolutionPost.username == username,
                    )
                )
            ).scalar_one_or_none()
            if sol:
                sol.url = url
                sol.vod_timestamp = vod_ts
            else:
                db.add(
                    SolutionPost(
                        problem_slug=slug,
                        platform="twitch",
                        username=username,
                        url=url,
                        vod_timestamp=vod_ts,
                    )
                )
            await db.commit()

        log.info("Logged solution from %s for %s", payload.chatter.name, slug)

    @commands.command(name="lc")
    async def leetcode_command(self, ctx: commands.Context):
        """
        !lc          — show the current LeetCode problem (anyone)
        !lc <url>    — log a new problem (broadcaster/mod only)
        """
        args = ctx.content.split()

        if len(args) < 2:
            if self.cooldowns.check("lc", ctx.author.id, CommandCooldowns.LC):
                return
            self.cooldowns.record("lc", ctx.author.id)

            active_session = await get_active_session()
            if not active_session:
                await ctx.reply("⚠️ No active stream session.")
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
                await ctx.reply("No LeetCode problem logged yet.")
            else:
                await ctx.reply(attempt.url)
            return

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
                    session_id=active_session.id, event_type="problem_attempt"
                )
                db.add(event)
                await db.flush()
                db.add(
                    ProblemAttempt(
                        stream_event_id=event.id,
                        slug=slug,
                        title=title_str,
                        url=url,
                        difficulty=data["difficulty"],
                        rating=rating_int,
                        vod_timestamp=vod_ts,
                    )
                )
                await db.commit()

            if rating_int is not None:
                reply = f"✅ {title_str} | {data['difficulty']} | Rating: {rating_int} @ {vod_ts}"
            else:
                reply = f"✅ {title_str} | {data['difficulty']} @ {vod_ts}"
            await ctx.reply(reply)
            log.info("Logged LeetCode problem: %s", title_str)
        except Exception:
            log.error("DB error logging LC problem", exc_info=True)
            await ctx.reply("❌ Failed to save to DB.")
