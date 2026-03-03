# couchd/platforms/twitch/components/general_commands.py
import logging
from twitchio.ext import commands

from couchd.core.config import settings
from couchd.core.db import get_session
from couchd.core.models import StreamEvent, ClipLog, IdeaPost
from couchd.core.clients.youtube import YouTubeRSSClient
from couchd.core.constants import CommandCooldowns, ClipConfig
from couchd.platforms.twitch.components.cooldowns import CooldownManager
from couchd.core.utils import get_active_session, compute_vod_timestamp

log = logging.getLogger(__name__)


class GeneralCommands(commands.Component):
    def __init__(self, bot: commands.Bot, youtube_client: YouTubeRSSClient | None):
        self.bot = bot
        self.youtube_client = youtube_client
        self.cooldowns = CooldownManager()

    @commands.command(name="commands")
    async def commands_list(self, ctx: commands.Context):
        """!commands — list all available bot commands."""
        if self.cooldowns.check("commands", ctx.author.id, CommandCooldowns.COMMANDS):
            return
        self.cooldowns.record("commands", ctx.author.id)
        await ctx.reply(
            "Full command list: https://github.com/shassen14/boneless_couch/blob/main/docs/twitch-commands.md"
        )

    @commands.command(name="newvideo")
    async def newvideo_command(self, ctx: commands.Context):
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

    @commands.command(name="clip")
    async def clip_command(self, ctx: commands.Context):
        """!clip [title] — create a Twitch clip of this moment."""
        if self.cooldowns.check("clip", ctx.author.id, CommandCooldowns.CLIP):
            return
        self.cooldowns.record("clip", ctx.author.id)

        args = ctx.content.split(maxsplit=1)
        title = args[1].strip() if len(args) >= 2 else ClipConfig.DEFAULT_TITLE

        active_session = await get_active_session()
        if not active_session:
            await ctx.reply("⚠️ No active stream session.")
            return

        try:
            users = await self.bot.fetch_users(ids=[settings.TWITCH_OWNER_ID])
            created = await users[0].create_clip(
                token_for=settings.TWITCH_OWNER_ID,
                title=title,
                duration=ClipConfig.DURATION,
            )
        except Exception:
            log.error("Failed to create Twitch clip", exc_info=True)
            await ctx.reply("❌ Could not create clip.")
            return

        url = ClipConfig.URL_BASE + created.id
        vod_ts = compute_vod_timestamp(active_session.start_time)

        try:
            async with get_session() as db:
                event = StreamEvent(session_id=active_session.id, event_type="clip")
                db.add(event)
                await db.flush()
                db.add(
                    ClipLog(
                        stream_event_id=event.id,
                        clip_id=created.id,
                        title=title,
                        url=url,
                        clipped_by=ctx.author.name,
                        platform="twitch",
                        vod_timestamp=vod_ts,
                    )
                )
                await db.commit()
        except Exception:
            log.error("DB error logging clip", exc_info=True)

        await ctx.reply(f"✂️ Clip created: {url}")
        log.info("Clip created: %s (%s)", title, url)

    @commands.command(name="idea")
    async def idea_command(self, ctx: commands.Context):
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
            db.add(IdeaPost(text=text, submitted_by=ctx.author.name, platform="twitch"))
            await db.commit()

        await ctx.reply("💡 Idea noted! The community can vote on it in Discord.")
        log.info("Idea submitted by %s: %s", ctx.author.name, text)
