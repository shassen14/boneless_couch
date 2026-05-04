# couchd/platforms/youtube/components/general_commands.py
import logging

from couchd.core.db import get_session
from couchd.core.models import IdeaPost
from couchd.core.clients.youtube import YouTubeRSSClient
from couchd.core.constants import CommandCooldowns, Platform
from couchd.core.cooldowns import CooldownManager

log = logging.getLogger(__name__)


class GeneralCommands:
    def __init__(self, youtube_client: YouTubeRSSClient | None):
        self.youtube_client = youtube_client
        self.cooldowns = CooldownManager()

    async def cmd_commands(self, ctx) -> None:
        """!commands — list all available bot commands."""
        if self.cooldowns.check("commands", ctx.author.id, CommandCooldowns.COMMANDS):
            return
        self.cooldowns.record("commands", ctx.author.id)
        await ctx.reply(
            "Full command list: https://github.com/shassen14/boneless_couch/blob/main/docs/twitch-commands.md"
        )

    async def cmd_newvideo(self, ctx) -> None:
        """!newvideo — show the title and link of the latest YouTube video."""
        if self.cooldowns.check("newvideo", ctx.author.id, CommandCooldowns.NEWVIDEO):
            return
        self.cooldowns.record("newvideo", ctx.author.id)

        if not self.youtube_client:
            await ctx.reply("YouTube is not configured.")
            return

        video = await self.youtube_client.get_latest_video()
        if not video:
            await ctx.reply("Could not fetch the latest video right now.")
            return

        await ctx.reply(f"{video['title']} → {video['video_url']}")

    async def cmd_idea(self, ctx) -> None:
        """!idea <text> — submit a community idea."""
        if self.cooldowns.check("idea", ctx.author.id, CommandCooldowns.IDEA):
            return
        self.cooldowns.record("idea", ctx.author.id)

        args = ctx.content.split(maxsplit=1)
        if len(args) < 2 or not args[1].strip():
            await ctx.reply("Usage: !idea <your idea text>")
            return

        text = args[1].strip()
        async with get_session() as db:
            db.add(IdeaPost(text=text, submitted_by=ctx.author.name, platform=Platform.YOUTUBE.value))
            await db.commit()

        await ctx.reply("Idea noted! The community can vote on it in Discord.")
        log.info("Idea submitted by %s: %s", ctx.author.name, text)
