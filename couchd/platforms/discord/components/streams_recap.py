# couchd/platforms/discord/components/streams_recap.py
import logging
from dataclasses import dataclass, field as dc_field

import discord
from sqlalchemy import select

from couchd.core.db import get_session
from couchd.core.models import StreamSession, ProblemAttempt, ProjectLog, StreamEvent
from couchd.core.constants import StreamDefaults, BrandColors, MACRO_EVENT_TYPES, EventType, TASK_DONE

log = logging.getLogger(__name__)


@dataclass
class _Segment:
    event_type: str
    notes: str | None
    detail: object | None
    tasks: list[str] = dc_field(default_factory=list)


def _duration_str(session: StreamSession) -> str:
    if not session.start_time or not session.end_time:
        return "Unknown"
    total_seconds = int((session.end_time - session.start_time).total_seconds())
    hours, remainder = divmod(total_seconds, 3600)
    minutes, _ = divmod(remainder, 60)
    return f"{hours}h {minutes}m" if hours > 0 else f"{minutes}m"


def _task_lines(tasks: list[str]) -> str:
    return "".join(f"\n  → {t}" for t in tasks)


def _render_lc(seg: _Segment) -> str:
    a = seg.detail
    if a is None:
        return "- Unknown problem" + _task_lines(seg.tasks)
    text = f"[{a.title}]({a.url})" if a.url else a.title
    if a.difficulty:
        text += f" · {a.difficulty}"
    if a.rating is not None:
        text += f" · {a.rating}"
    if a.vod_timestamp:
        text += f" · `{a.vod_timestamp}`"
    return f"- {text}" + _task_lines(seg.tasks)


def _render_project(seg: _Segment) -> str:
    p = seg.detail
    if p is None:
        return "- Unknown project" + _task_lines(seg.tasks)
    text = f"[{p.title}]({p.url})" if p.url else p.title
    if p.description:
        text += f" · {p.description}"
    return f"- {text}" + _task_lines(seg.tasks)


def _render_simple(seg: _Segment) -> str:
    return f"- {seg.notes or '—'}" + _task_lines(seg.tasks)


def _add_field(embed: discord.Embed, name: str, segs: list[_Segment], renderer) -> None:
    value = "\n".join(renderer(s) for s in segs)
    if len(value) > 1024:
        value = value[:1021] + "..."
    embed.add_field(name=name, value=value, inline=False)


async def post_stream_recap(stream_session: StreamSession, channel):
    async with get_session() as db:
        all_events = (
            await db.execute(
                select(StreamEvent)
                .where(StreamEvent.session_id == stream_session.id)
                .order_by(StreamEvent.timestamp)
            )
        ).scalars().all()

        attempts_by_event = {
            a.stream_event_id: a
            for a in (
                await db.execute(
                    select(ProblemAttempt)
                    .join(StreamEvent)
                    .where(StreamEvent.session_id == stream_session.id)
                )
            ).scalars().all()
        }
        projects_by_event = {
            p.stream_event_id: p
            for p in (
                await db.execute(
                    select(ProjectLog)
                    .join(StreamEvent)
                    .where(StreamEvent.session_id == stream_session.id)
                )
            ).scalars().all()
        }

    segments: list[_Segment] = []
    for event in all_events:
        if event.event_type in MACRO_EVENT_TYPES:
            detail = attempts_by_event.get(event.id) or projects_by_event.get(event.id)
            segments.append(_Segment(event.event_type, event.notes, detail))
        elif event.event_type == EventType.TASK and event.notes and event.notes.lower() != TASK_DONE:
            if segments:
                segments[-1].tasks.append(event.notes)

    by_type: dict[str, list[_Segment]] = {}
    for seg in segments:
        by_type.setdefault(seg.event_type, []).append(seg)

    title = stream_session.title or StreamDefaults.TITLE.value
    category = stream_session.category or StreamDefaults.CATEGORY.value
    embed = discord.Embed(
        title="Stream Recap",
        description=f"**{title}**\nPlaying: {category}",
        color=BrandColors.TWITCH,
    )
    embed.add_field(name="Duration", value=_duration_str(stream_session), inline=True)
    if stream_session.peak_viewers is not None:
        embed.add_field(name="Peak Viewers", value=str(stream_session.peak_viewers), inline=True)

    if EventType.PROBLEM_ATTEMPT in by_type:
        segs = by_type[EventType.PROBLEM_ATTEMPT]
        _add_field(embed, f"LeetCode ({len(segs)} attempted)", segs, _render_lc)

    if EventType.PROJECT in by_type:
        _add_field(embed, "Projects", by_type[EventType.PROJECT], _render_project)

    if EventType.EDIT in by_type:
        _add_field(embed, "Video Editing", by_type[EventType.EDIT], _render_simple)

    if EventType.TOPIC in by_type:
        _add_field(embed, "Just Chatting", by_type[EventType.TOPIC], _render_simple)

    if EventType.GAME in by_type:
        _add_field(embed, "Gaming", by_type[EventType.GAME], _render_simple)

    target = channel
    if stream_session.discord_notification_message_id:
        try:
            live_msg = await channel.fetch_message(
                stream_session.discord_notification_message_id
            )
            if live_msg.embeds:
                updated = live_msg.embeds[0].copy()
                updated.title = (updated.title or "").replace("🟢", "🔴")
                await live_msg.edit(embed=updated)
            if live_msg.thread:
                target = live_msg.thread
        except Exception:
            log.warning("Could not fetch go-live message/thread; posting recap to channel.")

    try:
        await target.send(embed=embed)
        log.info("Sent stream recap to %s.", getattr(target, "name", str(target.id)))
    except Exception as e:
        log.error("Failed to send stream recap embed", exc_info=e)
