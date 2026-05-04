# couchd/core/clients/youtube_chat.py
import asyncio
import logging
import pickle
from pathlib import Path

import aiohttp
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow

from couchd.core.constants import YouTubeChatConfig

log = logging.getLogger(__name__)


class YouTubeChatClient:
    """
    Async client for YouTube Live Chat API (Data API v3).
    Auth: OAuth 2.0 via pickle token file (same pattern as content_os).
    HTTP: aiohttp — non-blocking for the polling loop.
    Token refresh: sync via google-auth, run in executor to avoid blocking.
    """

    def __init__(self, client_secret_file: str, token_file: str):
        self._secret_file = Path(client_secret_file)
        self._token_file = Path(token_file)
        self._creds = None

    # ------------------------------------------------------------------
    # Auth
    # ------------------------------------------------------------------

    def _load_or_refresh_creds(self):
        """Sync: load pickled creds, refresh if expired, run OAuth flow if missing."""
        creds = None
        if self._token_file.exists():
            with self._token_file.open("rb") as f:
                creds = pickle.load(f)

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(
                    str(self._secret_file), YouTubeChatConfig.SCOPES
                )
                creds = flow.run_local_server(port=0)
            with self._token_file.open("wb") as f:
                pickle.dump(creds, f)

        return creds

    async def authenticate(self):
        loop = asyncio.get_event_loop()
        self._creds = await loop.run_in_executor(None, self._load_or_refresh_creds)
        log.info("YouTube chat client authenticated.")

    async def _ensure_creds(self):
        if not self._creds or not self._creds.valid:
            loop = asyncio.get_event_loop()
            self._creds = await loop.run_in_executor(None, self._load_or_refresh_creds)

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self._creds.token}"}

    # ------------------------------------------------------------------
    # Broadcasts
    # ------------------------------------------------------------------

    async def get_live_chat_id(self) -> str | None:
        """Return the liveChatId for the currently active broadcast, or None."""
        await self._ensure_creds()
        url = f"{YouTubeChatConfig.API_BASE}/liveBroadcasts"
        params = {
            "part": "snippet",
            "broadcastStatus": YouTubeChatConfig.BROADCAST_STATUS,
            "broadcastType": "all",
            "maxResults": 5,
        }
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=self._headers(), params=params) as resp:
                if resp.status == 401:
                    self._creds = None
                    await self._ensure_creds()
                    async with session.get(url, headers=self._headers(), params=params) as retry:
                        data = await retry.json()
                else:
                    data = await resp.json()

        items = data.get("items", [])
        if not items:
            return None
        return items[0]["snippet"]["liveChatId"]

    # ------------------------------------------------------------------
    # Messages
    # ------------------------------------------------------------------

    async def poll_messages(
        self, live_chat_id: str, page_token: str | None = None
    ) -> tuple[list[dict], str | None, int]:
        """
        Returns (messages, next_page_token, poll_interval_ms).
        messages: list of raw API items with author + snippet filled.
        """
        await self._ensure_creds()
        url = f"{YouTubeChatConfig.API_BASE}/liveChat/messages"
        params = {
            "liveChatId": live_chat_id,
            "part": "snippet,authorDetails",
            "maxResults": YouTubeChatConfig.MAX_RESULTS,
        }
        if page_token:
            params["pageToken"] = page_token

        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=self._headers(), params=params) as resp:
                if resp.status == 401:
                    self._creds = None
                    await self._ensure_creds()
                    async with session.get(url, headers=self._headers(), params=params) as retry:
                        data = await retry.json()
                elif resp.status != 200:
                    log.error("poll_messages HTTP %s: %s", resp.status, await resp.text())
                    return [], page_token, YouTubeChatConfig.DEFAULT_POLL_MS
                else:
                    data = await resp.json()

        messages = data.get("items", [])
        next_token = data.get("nextPageToken")
        poll_ms = data.get("pollingIntervalMillis", YouTubeChatConfig.DEFAULT_POLL_MS)
        return messages, next_token, int(poll_ms)

    async def send_message(self, live_chat_id: str, text: str) -> bool:
        await self._ensure_creds()
        url = f"{YouTubeChatConfig.API_BASE}/liveChat/messages"
        params = {"part": "snippet"}
        body = {
            "snippet": {
                "liveChatId": live_chat_id,
                "type": "textMessageEvent",
                "textMessageDetails": {"messageText": text},
            }
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url, headers=self._headers(), params=params, json=body
            ) as resp:
                if resp.status not in (200, 204):
                    log.error("send_message HTTP %s: %s", resp.status, await resp.text())
                    return False
        return True

    # ------------------------------------------------------------------
    # Moderation
    # ------------------------------------------------------------------

    async def delete_message(self, message_id: str) -> bool:
        await self._ensure_creds()
        url = f"{YouTubeChatConfig.API_BASE}/liveChat/messages"
        async with aiohttp.ClientSession() as session:
            async with session.delete(
                url, headers=self._headers(), params={"id": message_id}
            ) as resp:
                if resp.status not in (200, 204):
                    log.error("delete_message HTTP %s", resp.status)
                    return False
        return True

    async def ban_user(
        self, live_chat_id: str, channel_id: str, duration_seconds: int | None = None
    ) -> bool:
        """None = permanent ban. Integer = timeout in seconds."""
        await self._ensure_creds()
        url = f"{YouTubeChatConfig.API_BASE}/liveChat/bans"
        body: dict = {
            "snippet": {
                "liveChatId": live_chat_id,
                "bannedUserDetails": {"channelId": channel_id},
            }
        }
        if duration_seconds is not None:
            body["snippet"]["type"] = "temporary"
            body["snippet"]["banDurationSeconds"] = duration_seconds
        else:
            body["snippet"]["type"] = "permanent"

        async with aiohttp.ClientSession() as session:
            async with session.post(
                url, headers=self._headers(), params={"part": "snippet"}, json=body
            ) as resp:
                if resp.status not in (200, 204):
                    log.error("ban_user HTTP %s: %s", resp.status, await resp.text())
                    return False
        return True

    async def unban_user(self, ban_id: str) -> bool:
        await self._ensure_creds()
        url = f"{YouTubeChatConfig.API_BASE}/liveChat/bans"
        async with aiohttp.ClientSession() as session:
            async with session.delete(
                url, headers=self._headers(), params={"id": ban_id}
            ) as resp:
                if resp.status not in (200, 204):
                    log.error("unban_user HTTP %s", resp.status)
                    return False
        return True
