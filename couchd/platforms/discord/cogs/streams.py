# couchd/platforms/discord/cogs/streams.py
import discord
from discord.ext import commands, tasks
import logging
import random
from datetime import datetime, timezone

from couchd.core.config import settings
from couchd.core.clients.twitch import TwitchClient
from couchd.core.db import get_session
from couchd.core.models import StreamSession, GuildConfig, ProblemAttempt, ProjectLog, StreamEvent
from couchd.core.constants import Platform, StreamDefaults, TwitchConfig, BrandColors
from sqlalchemy import select

log = logging.getLogger(__name__)


class StreamWatcherCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.twitch = TwitchClient()
        self.channel = settings.TWITCH_CHANNEL

        self.was_live_last_check = False
        self.check_twitch_status.start()

    def cog_unload(self):
        self.check_twitch_status.cancel()

    @tasks.loop(minutes=settings.TWITCH_POLL_RATE_MINUTES)
    async def check_twitch_status(self):
        await self.bot.wait_until_ready()

        log.debug(f"Checking {Platform.TWITCH.value} status for {self.channel}...")
        stream_data = await self.twitch.get_stream_status(self.channel)

        is_live_now = stream_data is not None

        if is_live_now and not self.was_live_last_check:
            log.info(f"{self.channel} went LIVE.")
            self.was_live_last_check = True
            await self.handle_stream_start(stream_data)

        elif not is_live_now and self.was_live_last_check:
            log.info(f"{self.channel} went OFFLINE.")
            self.was_live_last_check = False
            await self.handle_stream_end()

    async def handle_stream_start(self, stream_data: dict):
        title = stream_data.get("title", StreamDefaults.TITLE.value)
        category = stream_data.get("game_name", StreamDefaults.CATEGORY.value)

        stream_url = f"{TwitchConfig.BASE_URL}{self.channel}"

        raw_thumbnail = stream_data.get("thumbnail_url", "")
        thumbnail_url = raw_thumbnail.replace(
            TwitchConfig.THUMBNAIL_PLACEHOLDER_W, TwitchConfig.THUMBNAIL_WIDTH
        ).replace(TwitchConfig.THUMBNAIL_PLACEHOLDER_H, TwitchConfig.THUMBNAIL_HEIGHT)

        # Guard against bot restart mid-stream
        try:
            async with get_session() as session:
                existing = (await session.execute(
                    select(StreamSession)
                    .where(
                        (StreamSession.is_active == True)
                        & (StreamSession.platform == Platform.TWITCH.value)
                    )
                    .order_by(StreamSession.start_time.desc())
                )).scalars().first()
                if existing is not None:
                    log.info("Active StreamSession already exists; skipping creation (bot restart mid-stream).")
                    return
        except Exception as e:
            log.error("Failed to check existing StreamSession", exc_info=e)
            return

        # Post go-live embed; capture message_id before thread creation so an error
        # there doesn't lose the reference needed to attach the recap later.
        message_id = None
        try:
            async with get_session() as session:
                config = (await session.execute(
                    select(GuildConfig).where(GuildConfig.stream_updates_channel_id.isnot(None))
                )).scalar_one_or_none()

            if config and config.stream_updates_channel_id:
                discord_channel = self.bot.get_channel(config.stream_updates_channel_id)
                if discord_channel:
                    embed = discord.Embed(
                        title=f"🔴 {self.channel} is LIVE on Twitch!",
                        description=f"**{title}**\nPlaying: {category}",
                        url=stream_url,
                        color=BrandColors.TWITCH,
                    )
                    if thumbnail_url:
                        embed.set_image(url=f"{thumbnail_url}?r={random.randint(1, 99999)}")

                    msg = await discord_channel.send(embed=embed)
                    message_id = msg.id  # captured before thread creation

                    try:
                        await msg.create_thread(name=f"🔴 {self.channel} — {title}"[:100])
                    except Exception as e:
                        log.warning("Failed to create thread for go-live message", exc_info=e)

                    log.info(f"Sent go-live announcement to #{discord_channel.name}")
                else:
                    log.warning(
                        f"Configured stream updates channel ({config.stream_updates_channel_id}) is invisible to the bot."
                    )
            else:
                log.warning("No server has configured a stream_updates_channel_id. Skipping announcement.")
        except Exception as e:
            log.error("Failed to send Discord announcement", exc_info=e)

        # Save session; Discord post happens first so message_id is available in one insert.
        try:
            async with get_session() as session:
                session.add(StreamSession(
                    platform=Platform.TWITCH.value,
                    title=title,
                    category=category,
                    is_active=True,
                    discord_notification_message_id=message_id,
                ))
            log.info(f"Created StreamSession in DB (message_id={message_id}).")
        except Exception as e:
            log.error("Failed to create StreamSession in DB", exc_info=e)

    async def handle_stream_end(self):
        stream_session = None

        # Mark session inactive, set end_time
        try:
            async with get_session() as session:
                result = await session.execute(
                    select(StreamSession)
                    .where(
                        (StreamSession.is_active == True)
                        & (StreamSession.platform == Platform.TWITCH.value)
                    )
                    .order_by(StreamSession.start_time.desc())
                )
                stream_session = result.scalars().first()

                if stream_session is None:
                    log.warning(
                        "handle_stream_end: no active %s session found in DB.",
                        Platform.TWITCH.value,
                    )
                    return

                stream_session.is_active = False
                stream_session.end_time = datetime.now(timezone.utc)
                log.info(
                    "Marked active %s StreamSession (id=%d) as offline.",
                    Platform.TWITCH.value,
                    stream_session.id,
                )
        except Exception as e:
            log.error("Failed to close StreamSession in DB", exc_info=e)
            return

        # Find Discord channel
        try:
            async with get_session() as session:
                config = (await session.execute(
                    select(GuildConfig).where(GuildConfig.stream_updates_channel_id.isnot(None))
                )).scalar_one_or_none()

            if not config or not config.stream_updates_channel_id:
                log.warning("No stream_updates_channel_id configured. Skipping stream summary.")
                return

            discord_channel = self.bot.get_channel(config.stream_updates_channel_id)
            if not discord_channel:
                log.warning(
                    "Configured stream updates channel (%d) is invisible to the bot. Skipping summary.",
                    config.stream_updates_channel_id,
                )
                return
        except Exception as e:
            log.error("Failed to fetch GuildConfig for stream summary", exc_info=e)
            return

        await self._post_stream_summary(stream_session, discord_channel)

    async def _post_stream_summary(self, stream_session: StreamSession, channel):
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
            embed.add_field(name="Peak Viewers", value=str(stream_session.peak_viewers), inline=True)

        async with get_session() as db:
            attempts = (await db.execute(
                select(ProblemAttempt).join(StreamEvent)
                .where(StreamEvent.session_id == stream_session.id)
                .order_by(StreamEvent.timestamp)
            )).scalars().all()
            projects = (await db.execute(
                select(ProjectLog).join(StreamEvent)
                .where(StreamEvent.session_id == stream_session.id)
                .order_by(StreamEvent.timestamp)
            )).scalars().all()

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
            lines = [f"- [{p.title}]({p.url})" if p.url else f"- {p.title}" for p in projects]
            embed.add_field(name="GitHub Projects", value="\n".join(lines), inline=False)

        # Post recap in the go-live thread; fall back to channel if thread is unavailable.
        target = channel
        if stream_session.discord_notification_message_id:
            try:
                live_msg = await channel.fetch_message(stream_session.discord_notification_message_id)
                if live_msg.thread:
                    target = live_msg.thread
            except Exception:
                log.warning("Could not fetch go-live message/thread; posting recap to channel.")

        try:
            await target.send(embed=embed)
            log.info("Sent stream recap to %s.", getattr(target, "name", str(target.id)))
        except Exception as e:
            log.error("Failed to send stream recap embed", exc_info=e)


def setup(bot):
    bot.add_cog(StreamWatcherCog(bot))
