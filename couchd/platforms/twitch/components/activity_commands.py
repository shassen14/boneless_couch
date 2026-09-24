# couchd/platforms/twitch/components/activity_commands.py
import logging
from twitchio.ext import commands
from sqlalchemy import select

from couchd.core.db import get_session
from couchd.core.models import StreamEvent
from couchd.core.constants import (
    CommandCooldowns,
    MACRO_EVENT_TYPES,
    EventType,
    TASK_DONE,
    STATUS_ALIASES,
    MACRO_FALLBACK,
)
from couchd.platforms.twitch.components.cooldowns import CooldownManager
from couchd.core.utils import get_active_session, format_macro_event

log = logging.getLogger(__name__)


class ActivityCommands(commands.Component):
    def __init__(self):
        self.cooldowns = CooldownManager()

    async def _simple_event_command(
        self, ctx: commands.Context, event_type: str, label: str
    ) -> None:
        args = ctx.content.split(maxsplit=1)

        if len(args) < 2:
            if self.cooldowns.check(event_type, ctx.author.id, CommandCooldowns.SIMPLE):
                return
            self.cooldowns.record(event_type, ctx.author.id)
            active_session = await get_active_session()
            if not active_session:
                await ctx.reply("⚠️ No active stream session.")
                return
            async with get_session() as db:
                event = (
                    await db.execute(
                        select(StreamEvent)
                        .where(
                            StreamEvent.session_id == active_session.id,
                            StreamEvent.event_type == event_type,
                        )
                        .order_by(StreamEvent.timestamp.desc())
                        .limit(1)
                    )
                ).scalar_one_or_none()
            if not event or not event.notes:
                await ctx.reply(f"No {label.lower()} logged yet.")
            else:
                await ctx.reply(f"{label}: {event.notes}")
            return

        if not ctx.author.broadcaster and not ctx.author.moderator:
            return
        notes = args[1].strip()
        active_session = await get_active_session()
        if not active_session:
            await ctx.reply("⚠️ No active stream session found in DB.")
            return
        try:
            async with get_session() as db:
                db.add(
                    StreamEvent(
                        session_id=active_session.id, event_type=event_type, notes=notes
                    )
                )
                await db.commit()
            await ctx.reply(f"✅ {label}: {notes}")
            log.info("Logged %s: %s", event_type, notes)
        except Exception:
            log.error("DB error logging %s", event_type, exc_info=True)
            await ctx.reply("❌ Failed to save to DB.")

    # ------------------------------------------------------------------
    # !game / !edit / !topic  (macro subjects)
    # ------------------------------------------------------------------

    @commands.command(name="game")
    async def game_command(self, ctx: commands.Context):
        """!game / !game <name> — show or log current game being played."""
        await self._simple_event_command(ctx, EventType.GAME, "Now playing")

    @commands.command(name="edit")
    async def edit_command(self, ctx: commands.Context):
        """!edit / !edit <subject> — show or log current video editing subject."""
        await self._simple_event_command(ctx, EventType.EDIT, "Editing")

    @commands.command(name="topic")
    async def topic_command(self, ctx: commands.Context):
        """!topic / !topic <subject> — show or log current just chatting topic."""
        await self._simple_event_command(ctx, EventType.TOPIC, "Topic")

    # ------------------------------------------------------------------
    # !task  (micro subject — !task done to clear)
    # ------------------------------------------------------------------

    @commands.command(name="task")
    async def task_command(self, ctx: commands.Context):
        """!task / !task <detail> / !task done — show, set, or clear current micro-task."""
        args = ctx.content.split(maxsplit=1)

        if len(args) < 2:
            if self.cooldowns.check(EventType.TASK, ctx.author.id, CommandCooldowns.SIMPLE):
                return
            self.cooldowns.record(EventType.TASK, ctx.author.id)
            active_session = await get_active_session()
            if not active_session:
                await ctx.reply("⚠️ No active stream session.")
                return
            async with get_session() as db:
                event = (
                    await db.execute(
                        select(StreamEvent)
                        .where(
                            StreamEvent.session_id == active_session.id,
                            StreamEvent.event_type == EventType.TASK,
                        )
                        .order_by(StreamEvent.timestamp.desc())
                        .limit(1)
                    )
                ).scalar_one_or_none()
            active = event and event.notes and event.notes.lower() != TASK_DONE
            await ctx.reply(
                f"Current task: {event.notes}" if active else "No active task."
            )
            return

        if not ctx.author.broadcaster and not ctx.author.moderator:
            return
        notes = args[1].strip()
        active_session = await get_active_session()
        if not active_session:
            await ctx.reply("⚠️ No active stream session found in DB.")
            return
        try:
            async with get_session() as db:
                db.add(
                    StreamEvent(
                        session_id=active_session.id, event_type=EventType.TASK, notes=notes
                    )
                )
                await db.commit()
            reply = "✅ Task cleared." if notes.lower() == TASK_DONE else f"✅ Task: {notes}"
            await ctx.reply(reply)
            log.info("Logged task: %s", notes)
        except Exception:
            log.error("DB error logging task", exc_info=True)
            await ctx.reply("❌ Failed to save to DB.")

    # ------------------------------------------------------------------
    # !status  (macro + micro in one reply)
    # ------------------------------------------------------------------

    @commands.command(name="status", aliases=list(STATUS_ALIASES))
    async def status_command(self, ctx: commands.Context):
        """!status (!what, !wyd, !doing) — show current macro subject and active task."""
        if self.cooldowns.check("status", ctx.author.id, CommandCooldowns.SIMPLE):
            return
        self.cooldowns.record("status", ctx.author.id)
        active_session = await get_active_session()
        if not active_session:
            await ctx.reply("⚠️ No active stream session.")
            return
        async with get_session() as db:
            macro_event = (
                await db.execute(
                    select(StreamEvent)
                    .where(
                        StreamEvent.session_id == active_session.id,
                        StreamEvent.event_type.in_(MACRO_EVENT_TYPES),
                    )
                    .order_by(StreamEvent.timestamp.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
            task_event = (
                await db.execute(
                    select(StreamEvent)
                    .where(
                        StreamEvent.session_id == active_session.id,
                        StreamEvent.event_type == EventType.TASK,
                    )
                    .order_by(StreamEvent.timestamp.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
            macro_label = (
                await format_macro_event(db, macro_event) if macro_event else MACRO_FALLBACK
            )
        has_task = task_event and task_event.notes and task_event.notes.lower() != TASK_DONE
        if has_task:
            await ctx.reply(f"Current Status: {macro_label} ➔ Task: {task_event.notes}")
        else:
            await ctx.reply(f"Current Status: {macro_label}")
