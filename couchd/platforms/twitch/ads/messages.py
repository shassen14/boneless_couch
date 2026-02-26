# couchd/platforms/twitch/ads/messages.py
import random

# Probability of sending any message after an ad (avoids spamming every break).
_SEND_CHANCE = 0.65

_STATIC_POOL = [
    "Thanks for bearing with the ads! Follow so you never miss a stream! 🙏",
    "Ads keep the lights on. Appreciate the patience — back soon!",
    "Stretch break! Grab some water. Back in a moment.",
    "While we're here — drop a follow if you're enjoying the stream!",
]


def pick_ad_message(latest_video: dict | None = None) -> str | None:
    """
    Returns a chat message to post after an ad break, or None to stay silent.

    latest_video: dict with 'title' and 'video_url' keys from YouTubeRSSClient,
                  or None if YouTube is not configured.
    """
    if random.random() > _SEND_CHANCE:
        return None

    pool = list(_STATIC_POOL)
    if latest_video:
        pool.append(
            f"Catch my latest video while the ads run: "
            f"{latest_video['title']} → {latest_video['video_url']}"
        )

    return random.choice(pool)


_RETURN_POOL = [
    "We're back! Welcome back everyone 👋",
    "Ad break over — thanks for sticking around! 🙌",
    "And we're live again! Thanks for the patience 💪",
    "Back to it! Thanks for hanging tight ✌️",
    "Ads done — let's get back to it! 🚀",
]


def pick_return_message() -> str:
    """Returns a message to post when the ad break ends."""
    return random.choice(_RETURN_POOL)
