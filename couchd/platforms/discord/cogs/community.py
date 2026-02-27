# couchd/platforms/discord/cogs/community.py

import discord
from discord.ext import commands
import logging
from sqlalchemy import select

from couchd.core.config import settings
from couchd.core.db import get_session
from couchd.core.models import StreamEvent, ProblemAttempt, ProjectLog
from couchd.core.constants import BrandColors
from couchd.core.clients.youtube import YouTubeRSSClient

log = logging.getLogger(__name__)


class CommunityCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.youtube = YouTubeRSSClient() if settings.YOUTUBE_CHANNEL_ID else None

    @commands.slash_command(name="socials", description="Links to all of the streamer's social accounts.")
    async def socials(self, ctx: discord.ApplicationContext):
        embed = discord.Embed(title="Socials", color=BrandColors.PRIMARY)

        def _links(val: str) -> list[str]:
            return [s.strip() for s in val.split(",") if s.strip()]

        platforms = [
            ("Twitch", _links(settings.SOCIAL_TWITCH)),
            ("YouTube", _links(settings.SOCIAL_YOUTUBE)),
            ("GitHub", _links(settings.SOCIAL_GITHUB)),
        ]
        any_configured = False
        for name, links in platforms:
            if links:
                embed.add_field(name=name, value="\n".join(links), inline=False)
                any_configured = True

        if not any_configured:
            embed.description = "No socials configured yet."

        await ctx.respond(embed=embed)

    @commands.slash_command(name="latest", description="Latest YouTube upload.")
    async def latest(self, ctx: discord.ApplicationContext):
        if self.youtube is None:
            await ctx.respond("YouTube is not configured.", ephemeral=True)
            return

        await ctx.defer()
        video = await self.youtube.get_latest_video()
        if video is None:
            await ctx.followup.send("Could not fetch the latest video right now.")
            return

        embed = discord.Embed(
            title=video["title"],
            url=video["video_url"],
            color=BrandColors.YOUTUBE,
        )
        if video["thumbnail_url"]:
            embed.set_image(url=video["thumbnail_url"])

        await ctx.followup.send(embed=embed)

    @commands.slash_command(name="project", description="Most recent GitHub project from the last stream.")
    async def project(self, ctx: discord.ApplicationContext):
        await ctx.defer()
        async with get_session() as session:
            project = (await session.execute(
                select(ProjectLog)
                .join(StreamEvent)
                .order_by(StreamEvent.timestamp.desc())
                .limit(1)
            )).scalar_one_or_none()

        if project is None:
            await ctx.followup.send("No project has been logged yet.")
            return

        embed = discord.Embed(title=project.title, url=project.url, color=BrandColors.PRIMARY)
        await ctx.followup.send(embed=embed)

    @commands.slash_command(name="lc", description="Most recent LeetCode problem from the last stream.")
    async def lc(self, ctx: discord.ApplicationContext):
        await ctx.defer()
        async with get_session() as session:
            attempt = (await session.execute(
                select(ProblemAttempt)
                .join(StreamEvent)
                .order_by(StreamEvent.timestamp.desc())
                .limit(1)
            )).scalar_one_or_none()

        if attempt is None:
            await ctx.followup.send("No LeetCode problem has been logged yet.")
            return

        embed = discord.Embed(title=attempt.title, url=attempt.url, color=BrandColors.PRIMARY)
        if attempt.rating is not None:
            embed.add_field(name="Rating", value=str(attempt.rating), inline=True)
        if attempt.vod_timestamp:
            embed.add_field(name="VOD Timestamp", value=f"`{attempt.vod_timestamp}`", inline=True)

        await ctx.followup.send(embed=embed)


def setup(bot):
    bot.add_cog(CommunityCog(bot))
