# couchd/platforms/discord/cogs/clips.py
import logging

import discord
from discord.ext import commands, tasks
from sqlalchemy import select

from couchd.core.constants import BrandColors
from couchd.core.db import get_session
from couchd.core.models import ClipLog, GuildConfig, StreamEvent

log = logging.getLogger(__name__)


class ClipWatcherCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.post_clips.start()

    def cog_unload(self):
        self.post_clips.cancel()

    @tasks.loop(minutes=1)
    async def post_clips(self):
        await self.bot.wait_until_ready()

        async with get_session() as session:
            config = (await session.execute(
                select(GuildConfig).where(GuildConfig.clip_showcase_channel_id.isnot(None))
            )).scalar_one_or_none()

            if not config:
                return

            unposted = (await session.execute(
                select(ClipLog)
                .join(StreamEvent)
                .where(ClipLog.discord_message_id.is_(None))
            )).scalars().all()

            if not unposted:
                return

            channel = self.bot.get_channel(config.clip_showcase_channel_id)
            if not channel:
                log.warning("clip_showcase_channel_id %d not visible to bot", config.clip_showcase_channel_id)
                return

            for clip in unposted:
                embed = discord.Embed(
                    title=clip.title,
                    description=clip.url,
                    color=BrandColors.TWITCH,
                )
                try:
                    msg = await channel.send(embed=embed)
                    clip.discord_message_id = msg.id
                    log.info("Posted clip to #%s: %s", channel.name, clip.title)
                except Exception:
                    log.error("Failed to post clip %s", clip.clip_id, exc_info=True)

            await session.commit()


def setup(bot):
    bot.add_cog(ClipWatcherCog(bot))
