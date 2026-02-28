# couchd/core/clients/youtube.py
import aiohttp
import logging
import xml.etree.ElementTree as ET

from couchd.core.config import settings
from couchd.core.constants import YouTubeConfig

log = logging.getLogger(__name__)

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
        headers = {"User-Agent": "Mozilla/5.0 (compatible; BonelessCouchBot/1.0)"}
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers) as response:
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
            thumbnail_url = (
                thumbnail_el.get("url", "") if thumbnail_el is not None else ""
            )

            return {
                "video_id": video_id,
                "title": title,
                "thumbnail_url": thumbnail_url,
                "video_url": f"{YouTubeConfig.VIDEO_URL}{video_id}",
            }
        except Exception as e:
            log.error("Exception while fetching YouTube RSS feed", exc_info=e)
            return None
