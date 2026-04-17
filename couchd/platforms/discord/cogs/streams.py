# couchd/platforms/discord/cogs/streams.py
import asyncio
import json
import asyncpg
import discord
from discord.ext import commands
import logging
import random


from couchd.core.config import settings
from couchd.core.db import get_session, get_listener_connection
from couchd.core.models import StreamSession, GuildConfig
from couchd.core.constants import Platform, StreamDefaults, TwitchConfig, BrandColors
from couchd.core.utils import get_active_session
from couchd.core.clients.twitch import TwitchClient
from sqlalchemy import select
from couchd.platforms.discord.components.streams_recap import post_stream_recap

log = logging.getLogger(__name__)


class StreamWatcherCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.channel = settings.TWITCH_CHANNEL
        self._listener_conn: asyncpg.Connection | None = None
        self._keepalive_task: asyncio.Task | None = None

    @commands.Cog.listener()
    async def on_ready(self):
        if self._listener_conn is not None:
            return  # already initialized on a previous on_ready
        try:
            await self._connect_listener()
            self._keepalive_task = asyncio.create_task(self._keepalive_listener())
            log.info("Listening for stream events via PostgreSQL NOTIFY.")
        except Exception:
            log.error("Failed to set up PostgreSQL listener", exc_info=True)
        asyncio.create_task(self._startup_live_check())

    def cog_unload(self):
        if self._keepalive_task:
            self._keepalive_task.cancel()
        if self._listener_conn:
            asyncio.get_event_loop().create_task(self._listener_conn.close())

    async def _connect_listener(self):
        self._listener_conn = await get_listener_connection()
        await self._listener_conn.add_listener("stream_online", self._on_stream_online)
        await self._listener_conn.add_listener("stream_offline", self._on_stream_offline)

    async def _keepalive_listener(self):
        while True:
            await asyncio.sleep(60)
            try:
                await self._listener_conn.fetchval("SELECT 1")
            except Exception:
                log.warning("Listener connection lost — reconnecting.")
                try:
                    await self._listener_conn.close()
                except Exception:
                    pass
                await self._connect_listener()
                log.info("Listener connection re-established.")

    def _on_stream_online(self, _conn, _pid, _channel, payload):
        log.info("Received stream_online pg_notify.")
        asyncio.get_event_loop().create_task(self._handle_stream_online(payload))

    def _on_stream_offline(self, _conn, _pid, _channel, payload):
        log.info("Received stream_offline pg_notify.")
        asyncio.get_event_loop().create_task(self._handle_stream_offline(payload))

    async def _handle_stream_online(self, payload: str):
        try:
            await self.bot.wait_until_ready()
            await self.handle_stream_start(json.loads(payload))
        except Exception:
            log.error("Error handling stream_online notification", exc_info=True)

    async def _handle_stream_offline(self, payload: str):
        try:
            await self.bot.wait_until_ready()
            data = json.loads(payload) if payload else {}
            await self.handle_stream_end(data.get("session_id"))
        except Exception:
            log.error("Error handling stream_offline notification", exc_info=True)

    async def _startup_live_check(self):
        """Independent startup check — detects live stream without relying on pg_notify."""
        await self.bot.wait_until_ready()
        await asyncio.sleep(10)  # let pg_notify path arrive and commit first
        try:
            existing = await get_active_session()
            if existing:
                log.info("Startup check: active session id=%d found in DB.", existing.id)
                return
            stream_data = await TwitchClient().get_stream_status(settings.TWITCH_CHANNEL)
            if not stream_data:
                log.info("Startup check: %s is offline.", settings.TWITCH_CHANNEL)
                return
            log.info("Startup check: stream is live, creating session directly.")
            await self.handle_stream_start({
                "title": stream_data.get("title", ""),
                "category": stream_data.get("game_name", ""),
                "thumbnail_url": stream_data.get("thumbnail_url", ""),
            })
        except Exception:
            log.error("Error in startup live check", exc_info=True)

    async def handle_stream_start(self, data: dict):
        title = data.get("title") or StreamDefaults.TITLE.value
        category = data.get("category") or StreamDefaults.CATEGORY.value
        stream_url = f"{TwitchConfig.BASE_URL}{self.channel}"

        raw_thumbnail = data.get("thumbnail_url", "")
        thumbnail_url = raw_thumbnail.replace(
            TwitchConfig.THUMBNAIL_PLACEHOLDER_W, TwitchConfig.THUMBNAIL_WIDTH
        ).replace(TwitchConfig.THUMBNAIL_PLACEHOLDER_H, TwitchConfig.THUMBNAIL_HEIGHT)

        # Guard against duplicate (bot restart mid-stream or duplicate notify)
        try:
            async with get_session() as session:
                existing = (
                    await session.execute(
                        select(StreamSession)
                        .where(
                            (StreamSession.is_active == True)
                            & (StreamSession.platform == Platform.TWITCH.value)
                        )
                        .order_by(StreamSession.start_time.desc())
                    )
                ).scalars().first()
                if existing is not None:
                    log.info("Active StreamSession already exists; skipping creation.")
                    return
        except Exception as e:
            log.error("Failed to check existing StreamSession", exc_info=e)
            return

        # Post go-live embed
        message_id = None
        try:
            async with get_session() as session:
                config = (
                    await session.execute(
                        select(GuildConfig).where(
                            GuildConfig.stream_updates_channel_id.isnot(None)
                        )
                    )
                ).scalar_one_or_none()

            if config and config.stream_updates_channel_id:
                discord_channel = self.bot.get_channel(config.stream_updates_channel_id)
                if discord_channel:
                    embed = discord.Embed(
                        title=f"🟢 {self.channel} is LIVE on Twitch!",
                        description=f"**{title}**\nPlaying: {category}",
                        url=stream_url,
                        color=BrandColors.TWITCH,
                    )
                    if thumbnail_url:
                        embed.set_image(url=f"{thumbnail_url}?r={random.randint(1, 99999)}")

                    msg = await discord_channel.send(embed=embed)
                    message_id = msg.id

                    try:
                        await msg.create_thread(name=f"🟢 {self.channel} — {title}"[:100])
                    except Exception as e:
                        log.warning("Failed to create thread for go-live message", exc_info=e)

                    log.info("Sent go-live announcement to #%s", discord_channel.name)
                else:
                    log.warning(
                        "Configured stream updates channel (%d) is invisible to the bot.",
                        config.stream_updates_channel_id,
                    )
            else:
                log.warning("No server has configured a stream_updates_channel_id. Skipping announcement.")
        except Exception as e:
            log.error("Failed to send Discord announcement", exc_info=e)

        # Save session
        try:
            async with get_session() as session:
                session.add(
                    StreamSession(
                        platform=Platform.TWITCH.value,
                        title=title,
                        category=category,
                        is_active=True,
                        discord_notification_message_id=message_id,
                    )
                )
            log.info("Created StreamSession in DB (message_id=%s).", message_id)
        except Exception as e:
            log.error("Failed to create StreamSession in DB", exc_info=e)

    async def handle_stream_end(self, session_id: int | None = None):
        stream_session = None

        try:
            async with get_session() as session:
                if session_id is not None:
                    result = await session.execute(
                        select(StreamSession).where(StreamSession.id == session_id)
                    )
                else:
                    result = await session.execute(
                        select(StreamSession)
                        .where(StreamSession.platform == Platform.TWITCH.value)
                        .order_by(StreamSession.start_time.desc())
                    )
                stream_session = result.scalars().first()

                if stream_session is None:
                    log.warning("handle_stream_end: session not found (id=%s).", session_id)
                    return
        except Exception as e:
            log.error("Failed to fetch StreamSession for recap", exc_info=e)
            return

        try:
            async with get_session() as session:
                config = (
                    await session.execute(
                        select(GuildConfig).where(
                            GuildConfig.stream_updates_channel_id.isnot(None)
                        )
                    )
                ).scalar_one_or_none()

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

        await post_stream_recap(stream_session, discord_channel)


def setup(bot):
    bot.add_cog(StreamWatcherCog(bot))
