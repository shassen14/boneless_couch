# couchd/platforms/twitch/components/cf_commands.py
import logging
from twitchio.ext import commands
from sqlalchemy import select

from couchd.core.db import get_session
from couchd.core.models import StreamEvent, CFProblemAttempt
from couchd.core.constants import CommandCooldowns, EventType
from couchd.core.clients import codeforces as cf_client
from couchd.platforms.twitch.components.cooldowns import CooldownManager
from couchd.core.utils import get_active_session, compute_vod_timestamp

log = logging.getLogger(__name__)


class CFCommands(commands.Component):
    def __init__(self):
        self.cooldowns = CooldownManager()

    @commands.command(name="cf")
    async def cf_command(self, ctx: commands.Context):
        """!cf — show current CF problem. !cf <url> [title] — log it (mod/broadcaster only)."""
        args = ctx.content.split(maxsplit=1)

        if len(args) < 2:
            if self.cooldowns.check("cf", ctx.author.id, CommandCooldowns.LC):
                return
            self.cooldowns.record("cf", ctx.author.id)
            active_session = await get_active_session()
            if not active_session:
                await ctx.reply("⚠️ No active stream session.")
                return
            async with get_session() as db:
                attempt = (
                    await db.execute(
                        select(CFProblemAttempt)
                        .join(StreamEvent)
                        .where(StreamEvent.session_id == active_session.id)
                        .order_by(StreamEvent.timestamp.desc())
                        .limit(1)
                    )
                ).scalar_one_or_none()
            if not attempt:
                await ctx.reply("No Codeforces problem logged yet this stream.")
            else:
                description = cf_client.describe(
                    attempt.problem_id, attempt.title, attempt.rating
                )
                await ctx.reply(f"📌 {description} → {attempt.url}")
            return

        if not ctx.author.broadcaster and not ctx.author.moderator:
            return

        url, _, title = args[1].strip().partition(" ")
        problem = await cf_client.resolve_problem(url, title.strip() or None)
        if not problem:
            await ctx.reply("❌ Invalid Codeforces problem URL.")
            return

        contest_id, index = problem["contest_id"], problem["index"]
        canonical_url = problem["url"]
        active_session = await get_active_session()
        if not active_session:
            await ctx.reply("⚠️ No active stream session.")
            return

        vod_ts = compute_vod_timestamp(active_session.start_time)
        tags_str = ", ".join(problem["tags"]) if problem["tags"] else None

        try:
            async with get_session() as db:
                event = StreamEvent(
                    session_id=active_session.id,
                    event_type=EventType.CF_PROBLEM,
                )
                db.add(event)
                await db.flush()
                db.add(CFProblemAttempt(
                    stream_event_id=event.id,
                    contest_id=contest_id,
                    index=index,
                    title=problem["title"],
                    url=canonical_url,
                    rating=problem["rating"],
                    tags=tags_str,
                    vod_timestamp=vod_ts,
                ))
                await db.commit()
        except Exception:
            log.error("DB error logging CF problem %d%s", contest_id, index, exc_info=True)
            await ctx.reply("❌ Failed to save to DB.")
            return

        description = cf_client.describe(
            f"{contest_id}{index}", problem["title"], problem["rating"]
        )
        await ctx.reply(f"✅ CF: {description} → {canonical_url}")
        log.info("Logged CF problem %d%s: %s", contest_id, index, problem["title"])
