# couchd/platforms/youtube/components/activity_commands.py
import logging
from sqlalchemy import select

from couchd.core.db import get_session
from couchd.core.models import StreamEvent, ProblemAttempt, ProjectLog
from couchd.core.constants import CommandCooldowns, MACRO_EVENT_TYPES, EventType, TASK_DONE, Platform
from couchd.core.cooldowns import CooldownManager
from couchd.core.utils import get_active_session

log = logging.getLogger(__name__)


class ActivityCommands:
    def __init__(self):
        self.cooldowns = CooldownManager()

    async def _simple_event_command(self, ctx, event_type: str, label: str) -> None:
        args = ctx.content.split(maxsplit=1)

        if len(args) < 2:
            if self.cooldowns.check(event_type, ctx.author.id, CommandCooldowns.SIMPLE):
                return
            self.cooldowns.record(event_type, ctx.author.id)
            active_session = await get_active_session(Platform.YOUTUBE)
            if not active_session:
                await ctx.reply("No active stream session.")
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
        active_session = await get_active_session(Platform.YOUTUBE)
        if not active_session:
            await ctx.reply("No active stream session found in DB.")
            return
        try:
            async with get_session() as db:
                db.add(StreamEvent(
                    session_id=active_session.id, event_type=event_type, notes=notes
                ))
                await db.commit()
            await ctx.reply(f"{label}: {notes}")
            log.info("Logged %s: %s", event_type, notes)
        except Exception:
            log.error("DB error logging %s", event_type, exc_info=True)
            await ctx.reply("Failed to save to DB.")

    async def _format_macro(self, db, event: StreamEvent) -> str:
        if event.event_type == EventType.PROBLEM_ATTEMPT:
            attempt = (
                await db.execute(
                    select(ProblemAttempt).where(ProblemAttempt.stream_event_id == event.id)
                )
            ).scalar_one_or_none()
            return f"Solving [LeetCode: {attempt.title}]" if attempt else "Solving [LeetCode problem]"
        if event.event_type == EventType.PROJECT:
            proj = (
                await db.execute(
                    select(ProjectLog).where(ProjectLog.stream_event_id == event.id)
                )
            ).scalar_one_or_none()
            return f"Working on [{proj.title}]" if proj else "Working on [project]"
        labels = {
            EventType.GAME: "Playing",
            EventType.EDIT: "Editing",
            EventType.TOPIC: "Chatting about",
        }
        prefix = labels.get(event.event_type, event.event_type.capitalize())
        return f"{prefix} [{event.notes}]"

    async def cmd_game(self, ctx) -> None:
        await self._simple_event_command(ctx, EventType.GAME, "Now playing")

    async def cmd_edit(self, ctx) -> None:
        await self._simple_event_command(ctx, EventType.EDIT, "Editing")

    async def cmd_topic(self, ctx) -> None:
        await self._simple_event_command(ctx, EventType.TOPIC, "Topic")

    async def cmd_task(self, ctx) -> None:
        """!task / !task <detail> / !task done — show, set, or clear current micro-task."""
        args = ctx.content.split(maxsplit=1)

        if len(args) < 2:
            if self.cooldowns.check(EventType.TASK, ctx.author.id, CommandCooldowns.SIMPLE):
                return
            self.cooldowns.record(EventType.TASK, ctx.author.id)
            active_session = await get_active_session(Platform.YOUTUBE)
            if not active_session:
                await ctx.reply("No active stream session.")
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
            await ctx.reply(f"Current task: {event.notes}" if active else "No active task.")
            return

        if not ctx.author.broadcaster and not ctx.author.moderator:
            return
        notes = args[1].strip()
        active_session = await get_active_session(Platform.YOUTUBE)
        if not active_session:
            await ctx.reply("No active stream session found in DB.")
            return
        try:
            async with get_session() as db:
                db.add(StreamEvent(
                    session_id=active_session.id, event_type=EventType.TASK, notes=notes
                ))
                await db.commit()
            reply = "Task cleared." if notes.lower() == TASK_DONE else f"Task: {notes}"
            await ctx.reply(reply)
            log.info("Logged task: %s", notes)
        except Exception:
            log.error("DB error logging task", exc_info=True)
            await ctx.reply("Failed to save to DB.")

    async def cmd_status(self, ctx) -> None:
        """!status — show current macro subject and active task."""
        if self.cooldowns.check("status", ctx.author.id, CommandCooldowns.SIMPLE):
            return
        self.cooldowns.record("status", ctx.author.id)
        active_session = await get_active_session(Platform.YOUTUBE)
        if not active_session:
            await ctx.reply("No active stream session.")
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
                await self._format_macro(db, macro_event) if macro_event else "Just streaming"
            )
        has_task = task_event and task_event.notes and task_event.notes.lower() != TASK_DONE
        if has_task:
            await ctx.reply(f"Status: {macro_label} → Task: {task_event.notes}")
        else:
            await ctx.reply(f"Status: {macro_label}")
