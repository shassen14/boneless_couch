# couchd/platforms/twitch/components/utils.py
import datetime
import logging

from couchd.core.config import settings
from couchd.core.constants import FollowAgeConfig, TwitchAdDuration

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


def format_follow_age(followed_at: datetime.datetime) -> str:
    """Render a follow date as a human phrase, e.g. "1 year, 2 months, 3 days"."""
    delta = datetime.datetime.now(datetime.timezone.utc) - followed_at
    years, rest = divmod(max(delta.days, 0), FollowAgeConfig.DAYS_PER_YEAR)
    months, days = divmod(rest, FollowAgeConfig.DAYS_PER_MONTH)

    parts = [
        (years, "year"),
        (months, "month"),
        (days, "day"),
    ]
    named = [f"{value} {label}{'s' if value != 1 else ''}" for value, label in parts if value]
    return ", ".join(named) if named else "less than a day"
