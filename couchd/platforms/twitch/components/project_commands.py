# couchd/platforms/twitch/components/project_commands.py
import logging
from twitchio.ext import commands
from sqlalchemy import select

from couchd.core.db import get_session
from couchd.core.models import StreamEvent, ProjectLog
from couchd.core.clients.github import GitHubClient
from couchd.core.constants import CommandCooldowns
from couchd.platforms.twitch.components.cooldowns import CooldownManager
from couchd.core.utils import get_active_session

log = logging.getLogger(__name__)


class ProjectCommands(commands.Component):
    def __init__(self, github_client: GitHubClient):
        self.github_client = github_client
        self.cooldowns = CooldownManager()

    @commands.command(name="project")
    async def project_command(self, ctx: commands.Context):
        """
        !project          — show the current project (anyone)
        !project <url>    — set the active GitHub project (broadcaster/mod only)
        """
        args = ctx.content.split()

        if len(args) < 2:
            if self.cooldowns.check("project", ctx.author.id, CommandCooldowns.PROJECT):
                return
            self.cooldowns.record("project", ctx.author.id)

            active_session = await get_active_session()
            if not active_session:
                await ctx.reply("⚠️ No active stream session.")
                return

            async with get_session() as db:
                project = (
                    await db.execute(
                        select(ProjectLog)
                        .join(StreamEvent)
                        .where(StreamEvent.session_id == active_session.id)
                        .order_by(StreamEvent.timestamp.desc())
                        .limit(1)
                    )
                ).scalar_one_or_none()

            if not project:
                await ctx.reply("No project logged yet.")
            elif project.description:
                await ctx.reply(f"Now working on: {project.title} — {project.description}")
            else:
                await ctx.reply(f"Now working on: {project.title}")
            return

        if not ctx.author.broadcaster and not ctx.author.moderator:
            return

        url = args[1]
        try:
            path = url.rstrip("/").split("github.com/")[1]
            parts = path.split("/")
            owner, repo = parts[0], parts[1]
        except (IndexError, ValueError):
            await ctx.reply("Invalid GitHub URL.")
            return

        active_session = await get_active_session()
        if not active_session:
            await ctx.reply("⚠️ No active stream session found in DB.")
            return

        description = await self.github_client.fetch_repo(owner, repo)
        repo_name = f"{owner}/{repo}"

        try:
            async with get_session() as db:
                event = StreamEvent(session_id=active_session.id, event_type="project")
                db.add(event)
                await db.flush()
                db.add(
                    ProjectLog(
                        stream_event_id=event.id,
                        url=url,
                        title=repo_name,
                        description=description,
                    )
                )
                await db.commit()

            if description:
                await ctx.reply(f"Now working on: {repo_name} — {description}")
            else:
                await ctx.reply(f"Now working on: {repo_name}")
            log.info("Logged project: %s", repo_name)
        except Exception:
            log.error("DB error logging project", exc_info=True)
            await ctx.reply("❌ Failed to save to DB.")
