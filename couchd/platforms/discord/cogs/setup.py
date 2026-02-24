# couchd/platforms/discord/cogs/setup.py
import discord
from discord.ext import commands
import logging
from sqlalchemy import select
from couchd.core.db import get_session
from couchd.core.models import GuildConfig
from couchd.core.constants import BrandColors

log = logging.getLogger(__name__)


class SetupCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # Create a Slash Command Group to organize our setup commands
    setup_group = discord.SlashCommandGroup(
        "setup",
        "Configure server channels and settings.",
        default_member_permissions=discord.Permissions(administrator=True),
    )

    async def _update_channel_config(
        self,
        ctx: discord.ApplicationContext,
        channel: discord.TextChannel,
        field_name: str,
        friendly_name: str,
    ):
        """Helper function to update the database to avoid repeating code."""
        await ctx.defer(ephemeral=True)
        guild_id = ctx.guild.id

        try:
            async with get_session() as session:
                # 1. Try to find existing config
                stmt = select(GuildConfig).where(GuildConfig.guild_id == guild_id)
                result = await session.execute(stmt)
                config = result.scalar_one_or_none()

                # 2. If it doesn't exist, create it
                if not config:
                    config = GuildConfig(guild_id=guild_id)
                    session.add(config)

                # 3. Update the specific field dynamically
                setattr(config, field_name, channel.id)

                # Context manager automatically commits here

            # 4. Send success message
            embed = discord.Embed(
                title="Configuration Updated ✅",
                description=f"The **{friendly_name}** has been set to {channel.mention}.",
                color=BrandColors.SUCCESS,
            )
            await ctx.followup.send(embed=embed, ephemeral=True)
            log.info(f"Guild {guild_id} updated config: {field_name} = {channel.id}")

        except Exception as e:
            log.error(
                f"Failed to update {field_name} config for guild {guild_id}", exc_info=e
            )
            await ctx.followup.send(
                "❌ An error occurred while saving to the database.", ephemeral=True
            )

    @setup_group.command(
        name="welcome_channel", description="Set the channel for welcome messages."
    )
    async def set_welcome(
        self, ctx: discord.ApplicationContext, channel: discord.TextChannel
    ):
        await self._update_channel_config(
            ctx, channel, "welcome_channel_id", "Welcome Channel"
        )

    @setup_group.command(
        name="role_channel", description="Set the channel where users select roles."
    )
    async def set_role(
        self, ctx: discord.ApplicationContext, channel: discord.TextChannel
    ):
        await self._update_channel_config(
            ctx, channel, "role_select_channel_id", "Role Select Channel"
        )

    @setup_group.command(
        name="stream_updates_channel",
        description="Set the channel for go-live announcements.",
    )
    async def set_stream_updates(
        self, ctx: discord.ApplicationContext, channel: discord.TextChannel
    ):
        await self._update_channel_config(
            ctx, channel, "stream_updates_channel_id", "Stream Updates Channel"
        )

    @setup_group.command(
        name="video_updates_channel",
        description="Set the channel for YouTube/TikTok uploads.",
    )
    async def set_video_updates(
        self, ctx: discord.ApplicationContext, channel: discord.TextChannel
    ):
        await self._update_channel_config(
            ctx, channel, "video_updates_channel_id", "Video Updates Channel"
        )

    @setup_group.command(
        name="video_updates_role",
        description="Set the role to ping when a new video is posted.",
    )
    async def set_video_updates_role(
        self, ctx: discord.ApplicationContext, role: discord.Role
    ):
        await ctx.defer(ephemeral=True)
        guild_id = ctx.guild.id

        try:
            async with get_session() as session:
                stmt = select(GuildConfig).where(GuildConfig.guild_id == guild_id)
                result = await session.execute(stmt)
                config = result.scalar_one_or_none()

                if not config:
                    config = GuildConfig(guild_id=guild_id)
                    session.add(config)

                config.video_updates_role_id = role.id

            embed = discord.Embed(
                title="Configuration Updated ✅",
                description=f"The **Video Updates Role** has been set to {role.mention}.",
                color=BrandColors.SUCCESS,
            )
            await ctx.followup.send(embed=embed, ephemeral=True)
            log.info(f"Guild {guild_id} updated config: video_updates_role_id = {role.id}")
        except Exception as e:
            log.error(f"Failed to update video_updates_role_id for guild {guild_id}", exc_info=e)
            await ctx.followup.send(
                "❌ An error occurred while saving to the database.", ephemeral=True
            )


def setup(bot):
    bot.add_cog(SetupCog(bot))
