# couchd/platforms/discord/components/streams_recap.py
import logging
import discord
from sqlalchemy import select

from couchd.core.db import get_session
from couchd.core.models import StreamSession, ProblemAttempt, ProjectLog, StreamEvent
from couchd.core.constants import StreamDefaults, BrandColors

log = logging.getLogger(__name__)


async def post_stream_recap(stream_session: StreamSession, channel):
    duration_str = "Unknown"
    if stream_session.start_time and stream_session.end_time:
        delta = stream_session.end_time - stream_session.start_time
        total_seconds = int(delta.total_seconds())
        hours, remainder = divmod(total_seconds, 3600)
        minutes, _ = divmod(remainder, 60)
        duration_str = f"{hours}h {minutes}m" if hours > 0 else f"{minutes}m"

    title = stream_session.title or StreamDefaults.TITLE.value
    category = stream_session.category or StreamDefaults.CATEGORY.value

    embed = discord.Embed(
        title="Stream Recap",
        description=f"**{title}**\nPlaying: {category}",
        color=BrandColors.TWITCH,
    )
    embed.add_field(name="Duration", value=duration_str, inline=True)
    if stream_session.peak_viewers is not None:
        embed.add_field(
            name="Peak Viewers", value=str(stream_session.peak_viewers), inline=True
        )

    async with get_session() as db:
        attempts = (
            (
                await db.execute(
                    select(ProblemAttempt)
                    .join(StreamEvent)
                    .where(StreamEvent.session_id == stream_session.id)
                    .order_by(StreamEvent.timestamp)
                )
            )
            .scalars()
            .all()
        )
        projects = (
            (
                await db.execute(
                    select(ProjectLog)
                    .join(StreamEvent)
                    .where(StreamEvent.session_id == stream_session.id)
                    .order_by(StreamEvent.timestamp)
                )
            )
            .scalars()
            .all()
        )

    if attempts:
        lines = []
        for a in attempts:
            text = f"[{a.title}]({a.url})" if a.url else a.title
            if a.rating is not None:
                text += f" · {a.rating}"
            if a.vod_timestamp:
                text += f" · `{a.vod_timestamp}`"
            lines.append(f"- {text}")
        embed.add_field(
            name=f"LeetCode ({len(attempts)} attempted)",
            value="\n".join(lines),
            inline=False,
        )

    if projects:
        lines = [
            f"- [{p.title}]({p.url})" if p.url else f"- {p.title}" for p in projects
        ]
        embed.add_field(name="GitHub Projects", value="\n".join(lines), inline=False)

    target = channel
    if stream_session.discord_notification_message_id:
        try:
            live_msg = await channel.fetch_message(
                stream_session.discord_notification_message_id
            )
            if live_msg.thread:
                target = live_msg.thread
        except Exception:
            log.warning(
                "Could not fetch go-live message/thread; posting recap to channel."
            )

    try:
        await target.send(embed=embed)
        log.info("Sent stream recap to %s.", getattr(target, "name", str(target.id)))
    except Exception as e:
        log.error("Failed to send stream recap embed", exc_info=e)
