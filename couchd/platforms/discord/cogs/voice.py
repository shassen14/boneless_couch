# couchd/platforms/discord/cogs/voice.py
import logging
import discord
from discord.ext import commands
from couchd.core.clients import veil

log = logging.getLogger(__name__)


class VoiceWatcherCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ) -> None:
        joined = before.channel is None and after.channel is not None
        left = before.channel is not None and after.channel is None

        if joined:
            await veil.post_event("discord.voice.join", {
                "user_id": str(member.id),
                "username": member.name,
                "display_name": member.display_name,
                "avatar_url": str(member.display_avatar.url),
                "channel_id": str(after.channel.id),
                "channel_name": after.channel.name,
            })
            return

        if left:
            await veil.post_event("discord.voice.leave", {
                "user_id": str(member.id),
                "username": member.name,
                "channel_id": str(before.channel.id),
            })
            return

        # Same channel — check for mute/deafen changes
        mute_changed = (
            before.self_mute != after.self_mute
            or before.self_deaf != after.self_deaf
        )
        if mute_changed:
            await veil.post_event("discord.voice.mute", {
                "user_id": str(member.id),
                "self_mute": after.self_mute,
                "self_deaf": after.self_deaf,
            })


def setup(bot):
    bot.add_cog(VoiceWatcherCog(bot))
