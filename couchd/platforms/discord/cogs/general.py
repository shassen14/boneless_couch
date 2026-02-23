# couchd/platforms/discord/cogs/general.py

import discord
from discord.ext import commands
import logging

from couchd.core.db import get_session
from couchd.core.models import GuildConfig
from sqlalchemy import select


log = logging.getLogger(__name__)


class GeneralCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # 1. THE SYNC COMMAND (Now Admin-only instead of hardcoded owner)
    @commands.slash_command(
        name="sync",
        description="Sync commands globally (Admins only)",
        default_member_permissions=discord.Permissions(administrator=True),
    )
    async def sync(self, ctx: discord.ApplicationContext):
        log.info(f"Sync command triggered by admin {ctx.author.name}")
        await ctx.defer(ephemeral=True)
        try:
            # In py-cord, this forces a sync but doesn't return a list.
            # If it doesn't throw an error, it was successful!
            await self.bot.sync_commands()

            log.info("Successfully synced commands globally.")
            await ctx.followup.send("✅ Commands synced successfully.", ephemeral=True)
        except Exception as e:
            log.error("Failed to sync commands.", exc_info=e)
            await ctx.followup.send(f"❌ Failed to sync commands: {e}", ephemeral=True)

    # 2. THE PING COMMAND
    @commands.slash_command(
        name="ping",
        description="Check if the bot is responsive. (Admins only)",
        default_member_permissions=discord.Permissions(administrator=True),
    )
    async def ping(self, ctx: discord.ApplicationContext):
        await ctx.respond(
            f"Pong! Latency is {self.bot.latency*1000:.2f}ms", ephemeral=True
        )

    # 3. THE MEMBERCOUNT COMMAND
    @commands.slash_command(
        name="membercount",
        description="Check if the bot can see server members. (Admins only)",
        default_member_permissions=discord.Permissions(administrator=True),
    )
    async def member_count(self, ctx: discord.ApplicationContext):
        guild = ctx.guild
        if guild:
            member_count = guild.member_count
            await ctx.respond(
                f"I can see {member_count} members in this server. ✅", ephemeral=True
            )
        else:
            await ctx.respond(
                "This command can only be used in a server.", ephemeral=True
            )

    # 4. THE DBTEST COMMAND
    @commands.slash_command(
        name="dbtest",
        description="Test Database connection. (Admins only)",
        default_member_permissions=discord.Permissions(administrator=True),
    )
    async def dbtest(self, ctx: discord.ApplicationContext):
        await ctx.defer(ephemeral=True)

        guild_id = ctx.guild.id

        # Use our new async context manager!
        try:
            async with get_session() as session:
                stmt = select(GuildConfig).where(GuildConfig.guild_id == guild_id)
                result = await session.execute(stmt)
                config = result.scalar_one_or_none()

                if config:
                    await ctx.followup.send(
                        f"✅ Found server config! Server ID: `{config.guild_id}`",
                        ephemeral=True,
                    )
                else:
                    new_config = GuildConfig(guild_id=guild_id)
                    session.add(new_config)
                    # Notice we removed `await session.commit()`.
                    # The get_session() context manager handles it for us now!
                    await ctx.followup.send(
                        "✅ Successfully created new server config record!",
                        ephemeral=True,
                    )

        except Exception as e:
            # Our context manager already rolled back the database and logged the error,
            # so we just need to inform the Discord user.
            await ctx.followup.send(f"❌ Database error: {e}", ephemeral=True)


def setup(bot):
    bot.add_cog(GeneralCog(bot))
