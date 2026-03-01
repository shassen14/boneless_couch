# couchd/platforms/discord/cogs/ideas.py
import logging
from datetime import datetime, timezone

import discord
from discord.ext import commands, tasks
from sqlalchemy import select

from couchd.core.db import get_session
from couchd.core.models import GuildConfig, IdeaPost
from couchd.core.constants import BrandColors, IdeaConfig

log = logging.getLogger(__name__)


class IdeasWatcherCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.check_ideas.start()

    def cog_unload(self):
        self.check_ideas.cancel()

    @tasks.loop(minutes=IdeaConfig.POLL_RATE_MINUTES)
    async def check_ideas(self):
        await self.bot.wait_until_ready()

        async with get_session() as db:
            config = (await db.execute(
                select(GuildConfig).where(GuildConfig.ideas_channel_id.isnot(None))
            )).scalar_one_or_none()

        if not config:
            return

        channel = self.bot.get_channel(config.ideas_channel_id)
        if not isinstance(channel, discord.TextChannel):
            return

        async with get_session() as db:
            unposted = (await db.execute(
                select(IdeaPost)
                .where(IdeaPost.discord_message_id.is_(None))
                .where(IdeaPost.removed_at.is_(None))
                .order_by(IdeaPost.created_at.asc())
            )).scalars().all()

        for idea in unposted:
            try:
                msg = await channel.send(embed=self._build_embed(idea))
                await msg.add_reaction(IdeaConfig.REACTION_SUPPORT)
                await msg.add_reaction(IdeaConfig.REACTION_AGAINST)
                async with get_session() as db:
                    row = await db.get(IdeaPost, idea.id)
                    row.discord_message_id = msg.id
                    await db.commit()
                log.info("Posted idea %d to channel %d", idea.id, config.ideas_channel_id)
            except Exception:
                log.error("Failed to post idea %d", idea.id, exc_info=True)

    def _build_embed(self, idea: IdeaPost) -> discord.Embed:
        embed = discord.Embed(
            title="💡 Community Idea",
            description=idea.text,
            color=BrandColors.PRIMARY,
        )
        embed.set_footer(text=f"Submitted by {idea.submitted_by} via {idea.platform}")
        return embed

    @commands.Cog.listener()
    async def on_raw_message_delete(self, payload: discord.RawMessageDeleteEvent):
        async with get_session() as db:
            idea = (await db.execute(
                select(IdeaPost).where(IdeaPost.discord_message_id == payload.message_id)
            )).scalar_one_or_none()
            if idea:
                idea.removed_at = datetime.now(timezone.utc)
                await db.commit()
                log.info("Soft-deleted idea %d (message %d removed)", idea.id, payload.message_id)

    @discord.slash_command(name="suggest", description="Submit a community idea.")
    async def suggest(self, ctx: discord.ApplicationContext, idea: str):
        async with get_session() as db:
            db.add(IdeaPost(
                text=idea,
                submitted_by=ctx.author.display_name,
                platform="discord",
            ))
            await db.commit()

        await ctx.respond("💡 Your idea has been noted! Check the ideas channel.", ephemeral=True)
        log.info("Idea submitted via /suggest by %s: %s", ctx.author.display_name, idea)


def setup(bot):
    bot.add_cog(IdeasWatcherCog(bot))
