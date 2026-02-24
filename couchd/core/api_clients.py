# couchd/core/api_clients.py
import aiohttp
import logging
import xml.etree.ElementTree as ET
from couchd.core.config import settings
from couchd.core.constants import YouTubeConfig

log = logging.getLogger(__name__)


class TwitchClient:
    """
    A reusable async client for interacting with the Twitch API.
    Handles automatic App Access Token generation and stream polling.
    """

    def __init__(self):
        self.client_id = settings.TWITCH_CLIENT_ID
        self.client_secret = settings.TWITCH_CLIENT_SECRET
        self.app_token = None

    async def _get_app_token(self) -> str:
        """Fetches a new App Access Token from Twitch."""
        url = f"https://id.twitch.tv/oauth2/token?client_id={self.client_id}&client_secret={self.client_secret}&grant_type=client_credentials"

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url) as response:
                    if response.status == 200:
                        data = await response.json()
                        self.app_token = data.get("access_token")
                        log.info("Successfully acquired Twitch App Access Token.")
                        return self.app_token
                    else:
                        log.error(
                            f"Failed to get Twitch token: {response.status} - {await response.text()}"
                        )
                        return None
        except Exception as e:
            log.error("Exception while fetching Twitch token", exc_info=e)
            return None

    async def get_stream_status(self, username: str) -> dict | None:
        """
        Checks if a user is live.
        Returns the stream data dict if live, or None if offline/error.
        """
        if not self.app_token:
            await self._get_app_token()

        if not self.app_token:
            return None  # Couldn't get a token

        url = f"https://api.twitch.tv/helix/streams?user_login={username}"
        headers = {
            "Client-ID": self.client_id,
            "Authorization": f"Bearer {self.app_token}",
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers) as response:
                    # If token expired (401), get a new one and retry once
                    if response.status == 401:
                        log.warning("Twitch token expired. Refreshing...")
                        await self._get_app_token()
                        headers["Authorization"] = f"Bearer {self.app_token}"
                        async with session.get(url, headers=headers) as retry_response:
                            if retry_response.status == 200:
                                data = await retry_response.json()
                            else:
                                return None
                    elif response.status == 200:
                        data = await response.json()
                    else:
                        log.error(f"Twitch API Error: {response.status}")
                        return None

            # If the 'data' list has items, the user is live!
            if data and data.get("data"):
                return data["data"][0]  # Return the first stream object

            return None  # List is empty, user is offline

        except Exception as e:
            log.error("Exception while checking Twitch stream status", exc_info=e)
            return None


_RSS_NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "yt": "http://www.youtube.com/xml/schemas/2015",
    "media": "http://search.yahoo.com/mrss/",
}


class YouTubeRSSClient:
    """
    Fetches the latest upload from a YouTube channel's public Atom feed.
    No API key or quota required.
    """

    def __init__(self):
        self.channel_id = settings.YOUTUBE_CHANNEL_ID

    async def get_latest_video(self) -> dict | None:
        """
        Returns metadata for the most recently uploaded video, or None on error.
        Keys: video_id, title, thumbnail_url, video_url
        """
        url = YouTubeConfig.RSS_URL.format(channel_id=self.channel_id)
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    if response.status != 200:
                        log.error(f"YouTube RSS error: {response.status}")
                        return None
                    text = await response.text()

            root = ET.fromstring(text)
            entry = root.find("atom:entry", _RSS_NS)
            if entry is None:
                return None

            video_id = entry.findtext("yt:videoId", namespaces=_RSS_NS) or ""
            title = entry.findtext("atom:title", namespaces=_RSS_NS) or "Untitled"
            thumbnail_el = entry.find("media:group/media:thumbnail", _RSS_NS)
            thumbnail_url = thumbnail_el.get("url", "") if thumbnail_el is not None else ""

            return {
                "video_id": video_id,
                "title": title,
                "thumbnail_url": thumbnail_url,
                "video_url": f"{YouTubeConfig.VIDEO_URL}{video_id}",
            }
        except Exception as e:
            log.error("Exception while fetching YouTube RSS feed", exc_info=e)
            return None
