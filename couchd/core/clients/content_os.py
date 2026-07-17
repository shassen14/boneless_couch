# couchd/core/clients/content_os.py
"""Outbound notifications to content_os.

Lightweight by design: we send only the session id. content_os already has the
read API (sessions/markers/recap), so duplicating the marker payload in the push
body would be pointless. If content_os is unreachable, log and continue — a
publishing service being down must never block the stream lifecycle.

Disabled (no-op) unless ``CONTENT_OS_API_URL`` is set.
"""
import logging

import aiohttp

from couchd.core.config import settings

log = logging.getLogger(__name__)

# content_os's inbound push endpoint (see content_os api/routers/ingest.py).
_SESSION_AVAILABLE_PATH = "/api/ingest/session-available"
_TIMEOUT_SECONDS = 5


async def notify_session_end(session_id: int) -> None:
    """Tell content_os a session is available to scaffold into a VOD project.

    This only signals readiness — content_os does not download anything until the
    operator explicitly triggers a scaffold. Best-effort; never raises.
    """
    if not settings.CONTENT_OS_API_URL:
        return

    url = f"{settings.CONTENT_OS_API_URL}{_SESSION_AVAILABLE_PATH}"
    headers = {}
    if settings.CONTENT_OS_API_SECRET:
        headers["Authorization"] = f"Bearer {settings.CONTENT_OS_API_SECRET}"

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url,
                json={"session_id": session_id},
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=_TIMEOUT_SECONDS),
            ) as resp:
                if resp.status not in (200, 202, 204):
                    log.warning(
                        "content_os session-available %d → %d", session_id, resp.status
                    )
                else:
                    log.info("Notified content_os of session %d", session_id)
    except aiohttp.ClientConnectorError:
        log.warning("content_os unreachable; dropping session-available %d", session_id)
    except Exception:
        log.warning("content_os notify failed for session %d", session_id, exc_info=True)
