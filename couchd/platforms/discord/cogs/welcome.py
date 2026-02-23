# couchd/platforms/discord/cogs/welcome.py

import discord
import logging
from discord.ext import commands
from sqlalchemy import select
from couchd.core.db import get_session
from couchd.core.models import GuildConfig
from couchd.core.constants import BrandColors

# Get the logger for this specific cog
log = logging.getLogger(__name__)


class WelcomeCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        """
        Triggered when a new member joins the server.
        Sends a beautifully formatted embed welcome message.
        """
        log.info(f"on_member_join event triggered for user: {member.name}")

        if member.bot:
            return

        guild = member.guild

        try:
            async with get_session() as session:
                stmt = select(GuildConfig).where(GuildConfig.guild_id == guild.id)
                result = await session.execute(stmt)
                config = result.scalar_one_or_none()
        except Exception as e:
            log.error("Database error while fetching welcome config.", exc_info=e)
            return

        if not config or not config.welcome_channel_id:
            log.warning(f"No welcome channel configured for guild '{guild.name}'.")
            return

        # Fetch actual Discord channel objects using the IDs from the DB
        welcome_channel = guild.get_channel(config.welcome_channel_id)
        roles_channel = (
            guild.get_channel(config.role_select_channel_id)
            if config.role_select_channel_id
            else None
        )

        if not welcome_channel:
            log.error(
                f"Welcome channel ID {config.welcome_channel_id} not found in guild."
            )
            return

        # 1. Create the Embed object
        # We use a nice green color to match your 🌿 aesthetic
        embed = discord.Embed(
            title="Welcome to All Here 🌿",
            description=(
                "This is the community behind everything I build and stream.\n"
                "Whether you’re here from a video, a stream, or just exploring — you’re welcome.\n\n"
                "Jump in, share what you’re working on, or just hang out.\n"
                "Glad you’re here."
            ),
            color=BrandColors.PRIMARY,
        )

        # 2. Add the "Call to Action" as a specific field
        if roles_channel:
            embed.add_field(
                name="Next Steps",
                value=f"👉 Head over to {roles_channel.mention} to unlock your channels!",
                inline=False,
            )

        # 3. Add a personalized touch: The user's avatar in the top right corner
        if member.avatar:
            embed.set_thumbnail(url=member.avatar.url)

        # Add a small footer
        embed.set_footer(text="All Here | SamirHere")

        try:
            # We send the embed, but we also include 'content=member.mention' outside the embed.
            # This ensures the user actually gets a ping notification so they see the message!
            await welcome_channel.send(content=member.mention, embed=embed)
            log.info(f"Successfully sent embed welcome message for {member.name}.")

        except discord.errors.Forbidden:
            log.error("Permission error: Cannot send messages to the welcome channel.")
        except Exception as e:
            log.error("An unexpected error occurred.", exc_info=e)


def setup(bot):
    bot.add_cog(WelcomeCog(bot))
