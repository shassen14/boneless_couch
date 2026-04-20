# couchd/core/clients/veil.py
import logging
import aiohttp
from couchd.core.config import settings

log = logging.getLogger(__name__)


async def post_event(event_type: str, payload: dict) -> None:
    if not settings.VEIL_URL:
        return
    headers = {}
    if settings.VEIL_SECRET:
        headers["Authorization"] = f"Bearer {settings.VEIL_SECRET}"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{settings.VEIL_URL}/event",
                json={"type": event_type, "payload": payload},
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=5),
            ) as resp:
                if resp.status not in (200, 204):
                    log.warning("Veil POST %s → %d", event_type, resp.status)
                else:
                    log.debug("Veil POST %s → %d", event_type, resp.status)
    except Exception:
        log.warning("Veil POST error for %s", event_type, exc_info=True)
