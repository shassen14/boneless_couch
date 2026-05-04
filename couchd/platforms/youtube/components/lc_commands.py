# couchd/platforms/youtube/components/lc_commands.py
import logging
import re
from sqlalchemy import select

from couchd.core.db import get_session
from couchd.core.models import StreamEvent, ProblemAttempt, SolutionPost, ProblemPost
from couchd.core.clients.leetcode import LeetCodeClient
from couchd.core.clients.youtube_chat import YouTubeChatClient
from couchd.core.constants import CommandCooldowns, Platform
from couchd.core.cooldowns import CooldownManager
from couchd.core.moderation import ModerationEngine
from couchd.core.utils import get_active_session, compute_vod_timestamp

log = logging.getLogger(__name__)

_LC_SUBMISSION_SLUG = re.compile(r"leetcode\.com/problems/([\w-]+)/submissions/\d+")
_LC_SUBMISSION_BARE = re.compile(r"leetcode\.com/submissions/detail/\d+")
_URL_RE = re.compile(r"https?://\S+")


class LCCommands:
    def __init__(
        self,
        lc_client: LeetCodeClient,
        mod_engine: ModerationEngine,
        chat_client: YouTubeChatClient,
    ):
        self.lc_client = lc_client
        self.mod_engine = mod_engine
        self.chat_client = chat_client
        self.cooldowns = CooldownManager()

    async def on_message(self, raw: dict, text: str) -> None:
        await self._check_solution_url(raw, text)

    async def _check_solution_url(self, raw: dict, text: str) -> None:
        slug_match = _LC_SUBMISSION_SLUG.search(text)
        if slug_match:
            slug = slug_match.group(1)
        elif _LC_SUBMISSION_BARE.search(text):
            slug = None
        else:
            return

        url_match = _URL_RE.search(text)
        if not url_match:
            return
        url = url_match.group(0)

        author_details = raw.get("authorDetails", {})
        username = author_details.get("displayName", "unknown")
        active_session = await get_active_session(Platform.YOUTUBE)

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

            vod_ts = compute_vod_timestamp(active_session.start_time) if active_session else None
            sol = (
                await db.execute(
                    select(SolutionPost).where(
                        SolutionPost.problem_slug == slug,
                        SolutionPost.platform == Platform.YOUTUBE.value,
                        SolutionPost.username == username,
                    )
                )
            ).scalar_one_or_none()
            if sol:
                sol.url = url
                sol.vod_timestamp = vod_ts
            else:
                db.add(SolutionPost(
                    problem_slug=slug,
                    platform=Platform.YOUTUBE.value,
                    username=username,
                    url=url,
                    vod_timestamp=vod_ts,
                ))
            await db.commit()

        log.info("Logged YouTube solution from %s for %s", username, slug)

    async def cmd_lc(self, ctx) -> None:
        """
        !lc         — show current LeetCode problem (anyone)
        !lc <url>   — log a new problem (owner/mod only)
        """
        args = ctx.content.split()

        if len(args) < 2:
            if self.cooldowns.check("lc", ctx.author.id, CommandCooldowns.LC):
                return
            self.cooldowns.record("lc", ctx.author.id)

            active_session = await get_active_session(Platform.YOUTUBE)
            if not active_session:
                await ctx.reply("No active stream session.")
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

        active_session = await get_active_session(Platform.YOUTUBE)
        if not active_session:
            await ctx.reply("No active stream session found in DB.")
            return

        data = await self.lc_client.fetch_problem(slug)
        if not data:
            await ctx.reply("Could not fetch problem data from LeetCode.")
            return

        rating = self.lc_client.get_rating(data["id"])
        rating_int = round(rating) if rating is not None else None
        title_str = f"{data['id']}. {data['title']}"
        vod_ts = compute_vod_timestamp(active_session.start_time)

        try:
            async with get_session() as db:
                event = StreamEvent(session_id=active_session.id, event_type="problem_attempt")
                db.add(event)
                await db.flush()
                db.add(ProblemAttempt(
                    stream_event_id=event.id,
                    slug=slug,
                    title=title_str,
                    url=url,
                    difficulty=data["difficulty"],
                    rating=rating_int,
                    vod_timestamp=vod_ts,
                ))
                await db.commit()

            if rating_int is not None:
                reply = f"{title_str} | {data['difficulty']} | Rating: {rating_int} @ {vod_ts}"
            else:
                reply = f"{title_str} | {data['difficulty']} @ {vod_ts}"
            await ctx.reply(reply)
            log.info("Logged LC problem: %s", title_str)
        except Exception:
            log.error("DB error logging LC problem", exc_info=True)
            await ctx.reply("Failed to save to DB.")
