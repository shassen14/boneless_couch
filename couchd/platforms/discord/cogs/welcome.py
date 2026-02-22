# couchd/platforms/discord/cogs/welcome.py

import discord
import logging
from discord.ext import commands

# Get the logger for this specific cog
log = logging.getLogger(__name__)


class WelcomeCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        """
        This event is triggered when a new member joins the server.
        """
        # This is our key debugging line. If this doesn't show up, the bot never received the event.
        log.info(
            f"on_member_join event triggered for user: {member.name} in guild: {member.guild.name}"
        )

        if member.bot:
            log.warning(f"Member {member.name} is a bot. Ignoring.")
            return

        guild = member.guild
        welcome_channel = discord.utils.get(guild.text_channels, name="welcome")
        roles_channel = discord.utils.get(guild.text_channels, name="role-select")

        if not welcome_channel:
            log.error(f"Could not find #welcome channel in '{guild.name}'.")
            return

        if not roles_channel:
            log.error(f"Could not find #role-select channel in '{guild.name}'.")
            return

        message = (
            f"Welcome to the server, {member.mention}! 🎉\n\n"
            f"We're thrilled to have you here. To get started and unlock "
            f"the rest of the channels, please head over to {roles_channel.mention} "
            f"and select your interests!"
        )

        try:
            await welcome_channel.send(message)
            log.info(
                f"Successfully sent welcome message for {member.name} in '{guild.name}'."
            )
        except discord.errors.Forbidden:
            log.error(
                f"Permission error: Cannot send message to #{welcome_channel.name} in '{guild.name}'. Check bot permissions."
            )
        except Exception as e:
            log.error(
                "An unexpected error occurred when sending welcome message.", exc_info=e
            )


def setup(bot):
    bot.add_cog(WelcomeCog(bot))
