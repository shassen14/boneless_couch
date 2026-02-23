# couchd/platforms/discord/cogs/streams.py
import discord
from discord.ext import commands, tasks
import logging
import random

from couchd.core.config import settings
from couchd.core.api_clients import TwitchClient
from couchd.core.db import get_session
from couchd.core.models import StreamSession, GuildConfig
from couchd.core.constants import Platform, StreamDefaults, TwitchConfig, BrandColors
from sqlalchemy import select, update

log = logging.getLogger(__name__)


class StreamWatcherCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.twitch = TwitchClient()
        self.target_username = settings.TWITCH_TARGET_USERNAME

        self.was_live_last_check = False
        self.check_twitch_status.start()

    def cog_unload(self):
        self.check_twitch_status.cancel()

    @tasks.loop(minutes=settings.TWITCH_POLL_RATE_MINUTES)
    async def check_twitch_status(self):
        await self.bot.wait_until_ready()

        log.debug(
            f"Checking {Platform.TWITCH.value} status for {self.target_username}..."
        )
        stream_data = await self.twitch.get_stream_status(self.target_username)

        is_live_now = stream_data is not None

        if is_live_now and not self.was_live_last_check:
            log.info(f"{self.target_username} went LIVE.")
            self.was_live_last_check = True
            await self.handle_stream_start(stream_data)

        elif not is_live_now and self.was_live_last_check:
            log.info(f"{self.target_username} went OFFLINE.")
            self.was_live_last_check = False
            await self.handle_stream_end()

    async def handle_stream_start(self, stream_data: dict):
        title = stream_data.get("title", StreamDefaults.TITLE.value)
        category = stream_data.get("game_name", StreamDefaults.CATEGORY.value)

        # Building URLs dynamically
        stream_url = f"{TwitchConfig.BASE_URL}{self.target_username}"

        raw_thumbnail = stream_data.get("thumbnail_url", "")
        thumbnail_url = raw_thumbnail.replace(
            TwitchConfig.THUMBNAIL_PLACEHOLDER_W, TwitchConfig.THUMBNAIL_WIDTH
        ).replace(TwitchConfig.THUMBNAIL_PLACEHOLDER_H, TwitchConfig.THUMBNAIL_HEIGHT)

        # 1. Save to Database
        try:
            async with get_session() as session:
                new_stream = StreamSession(
                    platform=Platform.TWITCH.value,  # Uses Enum
                    title=title,
                    category=category,
                    is_active=True,
                )
                session.add(new_stream)
                log.info(
                    f"Created active StreamSession in DB for {Platform.TWITCH.value}."
                )
        except Exception as e:
            log.error("Failed to create StreamSession in DB", exc_info=e)

        # 2. Post to Discord
        try:
            async with get_session() as session:
                # Find the server that has configured a stream updates channel
                stmt = select(GuildConfig).where(
                    GuildConfig.stream_updates_channel_id.isnot(None)
                )
                result = await session.execute(stmt)
                config = result.scalar_one_or_none()

                if config and config.stream_updates_channel_id:
                    channel = self.bot.get_channel(config.stream_updates_channel_id)
                    if channel:
                        embed = discord.Embed(
                            title=f"🔴 {self.target_username} is LIVE on Twitch!",
                            description=f"**{title}**\nPlaying: {category}",
                            url=stream_url,
                            color=BrandColors.TWITCH,  # Uses standard Brand color
                        )
                        if thumbnail_url:
                            # Cache-busting parameter (safe random integer)
                            embed.set_image(
                                url=f"{thumbnail_url}?r={random.randint(1, 99999)}"
                            )

                        await channel.send(embed=embed)
                        log.info(f"Sent Go-Live announcement to #{channel.name}")
                    else:
                        log.warning(
                            f"Configured stream updates channel ({config.stream_updates_channel_id}) is invisible to the bot."
                        )
                else:
                    log.warning(
                        "No server has configured a stream_updates_channel_id. Skipping announcement."
                    )
        except Exception as e:
            log.error("Failed to send Discord announcement", exc_info=e)

    async def handle_stream_end(self):
        try:
            async with get_session() as session:
                # Update the active session for THIS platform to inactive
                stmt = (
                    update(StreamSession)
                    .where(
                        (StreamSession.is_active == True)
                        & (StreamSession.platform == Platform.TWITCH.value)
                    )
                    .values(is_active=False)
                )

                await session.execute(stmt)
                log.info(
                    f"Marked active {Platform.TWITCH.value} StreamSession as offline in database."
                )
        except Exception as e:
            log.error("Failed to close StreamSession in DB", exc_info=e)


def setup(bot):
    bot.add_cog(StreamWatcherCog(bot))
