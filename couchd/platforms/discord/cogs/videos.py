# couchd/platforms/discord/cogs/videos.py
import discord
from discord.ext import commands, tasks
import logging

from couchd.core.config import settings
from couchd.core.api_clients import YouTubeRSSClient
from couchd.core.db import get_session
from couchd.core.models import GuildConfig
from couchd.core.constants import BrandColors
from sqlalchemy import select

log = logging.getLogger(__name__)


class VideoWatcherCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.youtube = YouTubeRSSClient()
        self.last_seen_video_id: str | None = None

        if not settings.YOUTUBE_CHANNEL_ID:
            log.warning("YOUTUBE_CHANNEL_ID not set. VideoWatcherCog disabled.")
            return

        self.check_youtube_uploads.start()

    def cog_unload(self):
        self.check_youtube_uploads.cancel()

    @tasks.loop(minutes=settings.YOUTUBE_POLL_RATE_MINUTES)
    async def check_youtube_uploads(self):
        await self.bot.wait_until_ready()

        log.debug("Checking YouTube for new uploads...")
        video = await self.youtube.get_latest_video()
        if not video:
            return

        video_id = video["video_id"]

        if self.last_seen_video_id is None:
            self.last_seen_video_id = video_id
            log.info(f"YouTube tracker initialized with video_id={video_id}")
            return

        if video_id == self.last_seen_video_id:
            return

        log.info(f"New YouTube video detected: {video_id}")
        self.last_seen_video_id = video_id
        await self._announce_video(video)

    def _build_mentions(self, config: GuildConfig, video: dict) -> str:
        """
        Returns a space-separated string of role mention strings for this video.

        Currently uses only the default video_updates_role_id (catch-all).
        Future: query a VideoRoleMapping table for topic-specific roles and
        match them against video title/tags here. Additional role IDs would
        just be appended to role_ids before the return.
        """
        role_ids = []
        if config.video_updates_role_id:
            role_ids.append(config.video_updates_role_id)
        return " ".join(f"<@&{rid}>" for rid in role_ids)

    async def _announce_video(self, video: dict):
        embed = discord.Embed(
            title=video["title"],
            url=video["video_url"],
            color=BrandColors.YOUTUBE,
        )
        if video["thumbnail_url"]:
            embed.set_image(url=video["thumbnail_url"])

        try:
            async with get_session() as session:
                stmt = select(GuildConfig).where(
                    GuildConfig.video_updates_channel_id.isnot(None)
                )
                result = await session.execute(stmt)
                config = result.scalar_one_or_none()

            if not config or not config.video_updates_channel_id:
                log.warning("No video_updates_channel_id configured. Skipping announcement.")
                return

            channel = self.bot.get_channel(config.video_updates_channel_id)
            if not channel:
                log.warning(
                    f"Configured video updates channel ({config.video_updates_channel_id}) is invisible to the bot."
                )
                return

            mentions = self._build_mentions(config, video)
            content = f"{mentions} New video just dropped!" if mentions else "New video just dropped!"
            message = await channel.send(content=content, embed=embed)
            log.info(f"Sent YouTube video announcement to #{channel.name}")

            thread = await message.create_thread(
                name=video["title"][:100],
                auto_archive_duration=1440,
            )
            await thread.send("What did you think? Drop your thoughts below!")
            log.info(f"Created discussion thread: {thread.name}")
        except Exception as e:
            log.error("Failed to send YouTube video announcement", exc_info=e)


def setup(bot):
    bot.add_cog(VideoWatcherCog(bot))
