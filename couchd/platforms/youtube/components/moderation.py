# couchd/platforms/youtube/components/moderation.py
import logging

from couchd.core.clients.youtube_chat import YouTubeChatClient

log = logging.getLogger(__name__)


class ModerationCommands:
    def __init__(self, chat_client: YouTubeChatClient):
        self.chat_client = chat_client

    def _is_privileged(self, ctx) -> bool:
        return ctx.author.broadcaster or ctx.author.moderator

    async def cmd_delete(self, ctx) -> None:
        """!delete <message_id> — delete a specific chat message."""
        if not self._is_privileged(ctx):
            return
        args = ctx.content.split()
        if len(args) < 2:
            await ctx.reply("Usage: !delete <message_id>")
            return
        success = await self.chat_client.delete_message(args[1])
        if not success:
            await ctx.reply("Failed to delete message.")
        log.info("Deleted message %s by %s", args[1], ctx.author.name)

    async def cmd_timeout(self, ctx) -> None:
        """!timeout <channel_id> <seconds> — temporarily ban a viewer."""
        if not self._is_privileged(ctx):
            return
        args = ctx.content.split()
        if len(args) < 3:
            await ctx.reply("Usage: !timeout <channel_id> <seconds>")
            return
        channel_id = args[1]
        try:
            seconds = int(args[2])
        except ValueError:
            await ctx.reply("Duration must be a number of seconds.")
            return
        success = await self.chat_client.ban_user(ctx._live_chat_id, channel_id, seconds)
        if not success:
            await ctx.reply("Failed to timeout user.")
        else:
            log.info("Timed out channel %s for %ds by %s", channel_id, seconds, ctx.author.name)

    async def cmd_ban(self, ctx) -> None:
        """!ban <channel_id> — permanently ban a viewer."""
        if not self._is_privileged(ctx):
            return
        args = ctx.content.split()
        if len(args) < 2:
            await ctx.reply("Usage: !ban <channel_id>")
            return
        channel_id = args[1]
        success = await self.chat_client.ban_user(ctx._live_chat_id, channel_id, duration_seconds=None)
        if not success:
            await ctx.reply("Failed to ban user.")
        else:
            log.info("Banned channel %s by %s", channel_id, ctx.author.name)

    async def cmd_unban(self, ctx) -> None:
        """!unban <ban_id> — remove a ban (requires the ban ID from YouTube)."""
        if not self._is_privileged(ctx):
            return
        args = ctx.content.split()
        if len(args) < 2:
            await ctx.reply("Usage: !unban <ban_id>")
            return
        success = await self.chat_client.unban_user(args[1])
        if not success:
            await ctx.reply("Failed to unban.")
        else:
            log.info("Unbanned %s by %s", args[1], ctx.author.name)
