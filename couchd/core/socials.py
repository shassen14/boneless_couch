# couchd/core/socials.py
from couchd.core.config import settings


def all_links() -> list[dict[str, str]]:
    return settings.SOCIAL_LINKS


def format_for_chat(sep: str = " | ") -> str | None:
    """Return all links formatted for a single chat message, or None if none configured."""
    parts = [f"{s['name']}: {s['url']}" for s in settings.SOCIAL_LINKS]
    return sep.join(parts) if parts else None


def find_by_name(name: str) -> str | None:
    """Return the URL of the first entry whose name contains `name` (case-insensitive)."""
    needle = name.lower()
    for s in settings.SOCIAL_LINKS:
        if needle in s.get("name", "").lower():
            return s.get("url")
    return None


def timer_messages() -> list[str]:
    """One promo message per configured social, in config order."""
    return [f"Find us on {s['name']}! {s['url']}" for s in settings.SOCIAL_LINKS]
