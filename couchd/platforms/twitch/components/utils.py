# couchd/platforms/twitch/components/utils.py
import logging

from couchd.core.config import settings
from couchd.core.constants import TwitchAdDuration

log = logging.getLogger(__name__)


async def send_chat_message(bot, message: str) -> None:
    """Send a standalone message to the streamer's channel."""
    try:
        users = await bot.fetch_users(logins=[settings.TWITCH_CHANNEL])
        if not users:
            log.warning("send_chat_message: could not fetch channel user.")
            return
        await users[0].send_message(sender=settings.TWITCH_BOT_ID, message=message)
    except Exception:
        log.error("Failed to send chat message", exc_info=True)


def clamp_to_ad_duration(seconds: int) -> int:
    """Return the largest valid TwitchAdDuration value that is ≤ seconds."""
    valid = sorted(d.value for d in TwitchAdDuration)
    clamped = valid[0]
    for v in valid:
        if v <= seconds:
            clamped = v
    return clamped
