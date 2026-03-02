# couchd/platforms/discord/cogs/clips.py
import logging
import re

import discord
from discord.ext import commands, tasks
from sqlalchemy import select

from couchd.core.clients.twitch import TwitchClient
from couchd.core.constants import BrandColors
from couchd.core.db import get_session
from couchd.core.models import ClipLog, GuildConfig, StreamEvent

log = logging.getLogger(__name__)

_THUMB_SIZE_RE = re.compile(r"-\d+x\d+(?=\.jpg)")


def _full_res_thumbnail(thumbnail_url: str) -> str:
    return _THUMB_SIZE_RE.sub("-1920x1080", thumbnail_url)


class ClipWatcherCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.twitch = TwitchClient()
        self.post_clips.start()

    def cog_unload(self):
        self.post_clips.cancel()

    @tasks.loop(minutes=1)
    async def post_clips(self):
        await self.bot.wait_until_ready()

        async with get_session() as session:
            config = (
                await session.execute(
                    select(GuildConfig).where(
                        GuildConfig.clip_showcase_channel_id.isnot(None)
                    )
                )
            ).scalar_one_or_none()

            if not config:
                return

            unposted = (
                (
                    await session.execute(
                        select(ClipLog)
                        .join(StreamEvent)
                        .where(ClipLog.discord_message_id.is_(None))
                    )
                )
                .scalars()
                .all()
            )

            if not unposted:
                return

            channel = self.bot.get_channel(config.clip_showcase_channel_id)
            if not channel:
                log.warning(
                    "clip_showcase_channel_id %d not visible to bot",
                    config.clip_showcase_channel_id,
                )
                return

            for clip in unposted:
                clip_data = await self.twitch.get_clip(clip.clip_id)
                thumbnail = (
                    _full_res_thumbnail(clip_data["thumbnail_url"])
                    if clip_data and clip_data.get("thumbnail_url")
                    else None
                )

                embed = discord.Embed(
                    title=clip.title,
                    url=clip.url,
                    color=BrandColors.TWITCH,
                )
                if clip.clipped_by:
                    embed.set_footer(text=f"Clipped by {clip.clipped_by}")
                if thumbnail:
                    embed.set_image(url=thumbnail)

                try:
                    msg = await channel.send(embed=embed)
                    clip.discord_message_id = msg.id
                    await msg.create_thread(name=f"💬 {clip.title}"[:100])
                    log.info("Posted clip to #%s: %s", channel.name, clip.title)
                except Exception:
                    log.error("Failed to post clip %s", clip.clip_id, exc_info=True)

            await session.commit()


def setup(bot):
    bot.add_cog(ClipWatcherCog(bot))
