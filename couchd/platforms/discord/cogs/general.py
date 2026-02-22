# couchd/platforms/discord/cogs/general.py

import discord
from discord.ext import commands
import logging

log = logging.getLogger(__name__)


class GeneralCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.slash_command(name="ping", description="Check if the bot is responsive.")
    async def ping(self, ctx: discord.ApplicationContext):
        """A simple command to check bot latency."""
        await ctx.respond(f"Pong! Latency is {self.bot.latency*1000:.2f}ms")

    @commands.slash_command(
        name="membercount", description="Check if the bot can see server members."
    )
    async def member_count(self, ctx: discord.ApplicationContext):
        """
        A diagnostic command to verify that the Members Intent is working.
        `ctx.guild.member_count` requires the intent to be enabled.
        """
        # The 'guild' is the server where the command was used.
        # We get this from the 'context' (ctx) of the command.
        guild = ctx.guild
        if guild:
            member_count = guild.member_count
            await ctx.respond(
                f"I can see {member_count} members in this server. The Members Intent is working correctly! ✅"
            )
        else:
            await ctx.respond(
                "This command can only be used in a server.", ephemeral=True
            )


def setup(bot):
    bot.add_cog(GeneralCog(bot))
