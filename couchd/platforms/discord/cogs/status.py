# couchd/platforms/discord/cogs/status.py
import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Awaitable, Callable

import aiohttp
import discord
from discord.ext import commands, tasks
from sqlalchemy import select, text

from couchd.core.clients.twitch import TwitchClient
from couchd.core.clients.youtube import YouTubeRSSClient
from couchd.core.config import settings
from couchd.core.constants import BrandColors, LeetCodeConfig, StatusConfig
from couchd.core.db import get_session
from couchd.core.models import GuildConfig

log = logging.getLogger(__name__)


@dataclass
class HealthCheck:
    label: str
    check: Callable[[], Awaitable[tuple[bool, str]]]


class StatusWatcherCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._message_ids: dict[int, int] = {}  # guild_id -> message_id
        self._checks: list[HealthCheck] = [
            HealthCheck("Database", self._check_database),
            HealthCheck("Twitch API", self._check_twitch),
            HealthCheck("YouTube RSS", self._check_youtube),
            HealthCheck("LeetCode", self._check_leetcode),
        ]
        self.update_status.start()

    def cog_unload(self):
        self.update_status.cancel()

    @tasks.loop(minutes=StatusConfig.POLL_RATE_MINUTES)
    async def update_status(self):
        await self.bot.wait_until_ready()

        results: list[tuple[bool, str]] = list(
            await asyncio.gather(*(c.check() for c in self._checks))
        )
        embed = self._build_embed(results)

        async with get_session() as session:
            result = await session.execute(
                select(GuildConfig).where(GuildConfig.status_channel_id.isnot(None))
            )
            configs = result.scalars().all()

        for config in configs:
            await self._post_or_edit(config.guild_id, config.status_channel_id, embed)

    async def _check_database(self) -> tuple[bool, str]:
        try:
            async with get_session() as session:
                await session.execute(text("SELECT 1"))
            return True, "Connected"
        except Exception as e:
            return False, str(e)

    async def _check_twitch(self) -> tuple[bool, str]:
        try:
            await TwitchClient().get_stream_status(settings.TWITCH_CHANNEL)
            return True, "Connected"
        except Exception as e:
            return False, str(e)

    async def _check_youtube(self) -> tuple[bool, str]:
        if not settings.YOUTUBE_CHANNEL_ID:
            return True, "Not configured"
        try:
            video = await YouTubeRSSClient().get_latest_video()
            return True, "Connected" if video else "No videos"
        except Exception as e:
            return False, str(e)

    async def _check_leetcode(self) -> tuple[bool, str]:
        try:
            timeout = aiohttp.ClientTimeout(total=5)
            async with aiohttp.ClientSession() as session:
                async with session.head(
                    LeetCodeConfig.BASE_URL, timeout=timeout
                ) as resp:
                    if resp.status < 500:
                        return True, "Reachable"
                    return False, f"HTTP {resp.status}"
        except Exception as e:
            return False, str(e)

    def _build_embed(self, results: list[tuple[bool, str]]) -> discord.Embed:
        all_ok = all(ok for ok, _ in results)
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        embed = discord.Embed(
            title="🤖 Bot Status",
            color=BrandColors.SUCCESS if all_ok else BrandColors.ERROR,
        )
        for check, (ok, msg) in zip(self._checks, results):
            embed.add_field(
                name=check.label, value=f"{'✅' if ok else '❌'} {msg}", inline=False
            )
        embed.set_footer(text=f"Last updated: {now}")
        return embed

    async def _post_or_edit(self, guild_id: int, channel_id: int, embed: discord.Embed):
        channel = self.bot.get_channel(channel_id)
        if not channel:
            log.warning(f"Status channel {channel_id} not visible for guild {guild_id}")
            return

        message_id = self._message_ids.get(guild_id)
        if message_id:
            try:
                message = await channel.fetch_message(message_id)
                await message.edit(embed=embed)
                return
            except discord.NotFound:
                log.info(f"Status message gone for guild {guild_id}, reposting")

        # Bot restarted — scan recent history to find and reuse the existing status message
        async for msg in channel.history(limit=50):
            if msg.author == self.bot.user and msg.embeds and msg.embeds[0].title == "🤖 Bot Status":
                self._message_ids[guild_id] = msg.id
                await msg.edit(embed=embed)
                log.info(f"Recovered status message for guild {guild_id} after restart")
                return

        message = await channel.send(embed=embed)
        self._message_ids[guild_id] = message.id


def setup(bot):
    bot.add_cog(StatusWatcherCog(bot))
