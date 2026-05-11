# couchd/platforms/youtube/main.py
import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import text

import sentry_sdk
from couchd.core.config import settings
from couchd.core.logger import setup_logging
from couchd.core.db import get_session
from couchd.core.models import StreamSession
from couchd.core.constants import Platform
from google.auth.exceptions import RefreshError
from couchd.core.clients.youtube_chat import YouTubeChatClient
from couchd.core.clients.youtube import YouTubeRSSClient
from couchd.core.clients.leetcode import LeetCodeClient
from couchd.core.clients.github import GitHubClient
from couchd.core.clients import veil
from couchd.core.cooldowns import CooldownManager
from couchd.core.moderation import ModerationEngine
from couchd.core.constants import HoldSource
from couchd.core.utils import get_active_session
from couchd.platforms.youtube.components.lc_commands import LCCommands
from couchd.platforms.youtube.components.general_commands import GeneralCommands
from couchd.platforms.youtube.components.activity_commands import ActivityCommands
from couchd.platforms.youtube.components.project_commands import ProjectCommands
from couchd.platforms.youtube.components.moderation import ModerationCommands
from couchd.platforms.youtube.components.cf_commands import CFCommands
from couchd.platforms.youtube.components.timers import ChatTimers

if settings.SENTRY_DSN:
    sentry_sdk.init(dsn=settings.SENTRY_DSN)

setup_logging(webhook_url=settings.BOT_LOGS_WEBHOOK_URL, bot_name="youtube")
log = logging.getLogger(__name__)

COMMAND_PREFIX = "!"


@dataclass
class YouTubeAuthor:
    id: str           # channelId
    name: str         # displayName
    display_name: str
    is_moderator: bool
    is_owner: bool

    @property
    def broadcaster(self) -> bool:
        return self.is_owner

    @property
    def moderator(self) -> bool:
        return self.is_moderator


@dataclass
class YouTubeChatContext:
    """Duck-typed equivalent of twitchio's Context for use in command components."""
    author: YouTubeAuthor
    content: str        # full message text including the command prefix+name
    message_id: str
    _client: "YouTubeChatClient"
    _live_chat_id: str

    async def reply(self, text: str) -> None:
        await self._client.send_message(self._live_chat_id, text)


class YouTubeBot:
    def __init__(self):
        self.chat_client = YouTubeChatClient(
            client_secret_file=settings.YOUTUBE_CLIENT_SECRET_FILE,
            token_file=settings.YOUTUBE_CHAT_TOKEN_FILE,
        )
        self.lc_client = LeetCodeClient()
        self.github_client = GitHubClient()
        self.youtube_client = YouTubeRSSClient() if settings.YOUTUBE_CHANNEL_ID else None
        self.mod_engine = ModerationEngine(settings.MODERATION_PATTERNS)

        self._components: list = []
        self._live_chat_id: str | None = None
        self._page_token: str | None = None
        self.chat_timers = ChatTimers(self)

    def _setup_components(self):
        self._components = [
            LCCommands(self.lc_client, self.mod_engine, self.chat_client),
            GeneralCommands(self.youtube_client),
            ActivityCommands(),
            ProjectCommands(self.github_client),
            ModerationCommands(self.chat_client),
            CFCommands(),
        ]

    async def _get_or_refresh_chat_id(self) -> str | None:
        chat_id = await self.chat_client.get_live_chat_id()
        if chat_id != self._live_chat_id:
            if chat_id:
                log.info("Live chat ID: %s", chat_id)
            self._live_chat_id = chat_id
            self._page_token = None
        return self._live_chat_id

    async def _dispatch(self, raw: dict) -> None:
        snippet = raw.get("snippet", {})
        author_details = raw.get("authorDetails", {})

        msg_type = snippet.get("type")
        if msg_type != "textMessageEvent":
            return

        text = snippet.get("textMessageDetails", {}).get("messageText", "").strip()
        if not text.startswith(COMMAND_PREFIX):
            await self._handle_chat_message(raw, text)
            return

        author = YouTubeAuthor(
            id=author_details.get("channelId", ""),
            name=author_details.get("displayName", ""),
            display_name=author_details.get("displayName", ""),
            is_moderator=author_details.get("isChatModerator", False),
            is_owner=author_details.get("isChatOwner", False),
        )
        ctx = YouTubeChatContext(
            author=author,
            content=text,
            message_id=raw.get("id", ""),
            _client=self.chat_client,
            _live_chat_id=self._live_chat_id,
        )

        parts = text[len(COMMAND_PREFIX):].split(maxsplit=1)
        cmd_name = parts[0].lower() if parts else ""

        for component in self._components:
            handler = getattr(component, f"cmd_{cmd_name}", None)
            if handler:
                try:
                    await handler(ctx)
                except Exception:
                    log.error("Error in command !%s", cmd_name, exc_info=True)
                return

    async def _handle_chat_message(self, raw: dict, text: str) -> None:
        author_details = raw.get("authorDetails", {})
        message_id = raw.get("id", "")
        display_name = author_details.get("displayName", "")

        log.info("[YT CHAT] %s: %s", display_name, text)

        chat_payload = {
            "username": display_name,
            "display_name": display_name,
            "channel_id": author_details.get("channelId", ""),
            "message": text,
            "message_id": message_id,
            "platform": Platform.YOUTUBE.value,
            "is_moderator": author_details.get("isChatModerator", False),
            "is_owner": author_details.get("isChatOwner", False),
        }

        if self.mod_engine.is_flagged(text):
            self.mod_engine.add_pending(message_id, chat_payload, HoldSource.BONELESS_COUCH)
            log.info("[MOD] Held YouTube message %s from %s", message_id, display_name)
            await veil.post_event("modqueue.pending", {**chat_payload, "hold_sources": [HoldSource.BONELESS_COUCH]})
            return

        await veil.post_event("youtube.chat.message", chat_payload)

        for component in self._components:
            if hasattr(component, "on_message"):
                try:
                    await component.on_message(raw, text)
                except Exception:
                    log.error("Error in on_message handler", exc_info=True)

    async def _poll_loop(self) -> None:
        while True:
            try:
                live_chat_id = await self._get_or_refresh_chat_id()
                if not live_chat_id:
                    await asyncio.sleep(30)
                    continue

                messages, next_token, poll_ms = await self.chat_client.poll_messages(
                    live_chat_id, self._page_token
                )
                self._page_token = next_token

                for msg in messages:
                    await self._dispatch(msg)

                await asyncio.sleep(poll_ms / 1000)
            except RefreshError:
                log.critical("YouTube OAuth token revoked — restart the bot after re-authenticating.")
                await asyncio.sleep(3600)
            except Exception:
                log.error("Error in YouTube poll loop", exc_info=True)
                await asyncio.sleep(10)

    async def _on_modqueue_decision(self, message_id: str, decision: str, platform: str) -> None:
        if platform != Platform.YOUTUBE.value:
            return
        pending = self.mod_engine.get(message_id)
        if not pending:
            return
        if decision == "deny":
            await self.chat_client.delete_message(message_id)
            log.info("Deleted modqueue message %s from YouTube chat.", message_id)
        self.mod_engine.pop(message_id)

    async def _broadcast_lifecycle_loop(self) -> None:
        """Polls for broadcast start/end and mirrors the Twitch pg_notify pattern."""
        was_live = False
        while True:
            try:
                chat_id = await self.chat_client.get_live_chat_id()
                is_live = chat_id is not None

                if is_live and not was_live:
                    log.info("YouTube broadcast started.")
                    async with get_session() as db:
                        existing = await get_active_session(Platform.YOUTUBE)
                        if not existing:
                            db.add(StreamSession(
                                platform=Platform.YOUTUBE.value,
                                title="YouTube Stream",
                                is_active=True,
                                start_time=datetime.now(timezone.utc),
                            ))
                            await db.flush()
                            notify_payload = json.dumps({"title": "YouTube Stream", "category": "", "thumbnail_url": ""})
                            await db.execute(text("SELECT pg_notify('stream_online', :p)"), {"p": notify_payload})
                    was_live = True

                elif not is_live and was_live:
                    log.info("YouTube broadcast ended.")
                    async with get_session() as db:
                        from sqlalchemy import select
                        result = await db.execute(
                            select(StreamSession).where(
                                (StreamSession.is_active == True)
                                & (StreamSession.platform == Platform.YOUTUBE.value)
                            ).order_by(StreamSession.start_time.desc())
                        )
                        session = result.scalars().first()
                        if session:
                            session.is_active = False
                            session.end_time = datetime.now(timezone.utc)
                            await db.execute(
                                text("SELECT pg_notify('stream_offline', :p)"),
                                {"p": json.dumps({"session_id": session.id})},
                            )
                    was_live = False

            except RefreshError:
                log.critical("YouTube OAuth token revoked — restart the bot after re-authenticating.")
                await asyncio.sleep(3600)
            except Exception:
                log.error("Error in YouTube lifecycle loop", exc_info=True)

            await asyncio.sleep(60)

    async def run(self) -> None:
        await self.chat_client.authenticate()
        await self.lc_client.load_ratings()
        self._setup_components()

        log.info("-" * 40)
        log.info("YouTube Bot is ONLINE!")
        log.info("-" * 40)

        self.chat_timers.start()
        await asyncio.gather(
            self._poll_loop(),
            self._broadcast_lifecycle_loop(),
            veil.listen_decisions(self._on_modqueue_decision),
        )


if __name__ == "__main__":
    if not settings.YOUTUBE_CLIENT_SECRET_FILE:
        raise RuntimeError("YOUTUBE_CLIENT_SECRET_FILE is not set in .env")
    asyncio.run(YouTubeBot().run())
