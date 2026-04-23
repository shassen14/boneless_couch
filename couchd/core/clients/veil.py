# couchd/core/clients/veil.py
import asyncio
import logging
from collections.abc import Callable, Awaitable

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


async def _post(path: str) -> None:
    if not settings.VEIL_URL:
        return
    headers = {}
    if settings.VEIL_SECRET:
        headers["Authorization"] = f"Bearer {settings.VEIL_SECRET}"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{settings.VEIL_URL}{path}",
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=5),
            ) as resp:
                log.info("veil POST %s → %d", path, resp.status)
    except Exception:
        log.warning("Veil POST error for %s", path, exc_info=True)


async def alerts_on() -> None:
    await _post("/alerts/on")


async def alerts_off() -> None:
    await _post("/alerts/off")


async def clear_alert_queue() -> None:
    await _post("/alerts/queue/clear")


async def listen_decisions(
    on_decision: Callable[[str, str, str], Awaitable[None]],
    on_connect: Callable[[], Awaitable[None]] | None = None,
) -> None:
    """Connect to veil WS and call on_decision(message_id, decision, platform) for modqueue decisions."""
    if not settings.VEIL_URL:
        return
    ws_url = settings.VEIL_URL.replace("http://", "ws://").replace("https://", "wss://") + "/ws"
    delay = 1
    while True:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.ws_connect(ws_url) as ws:
                    log.info("Connected to veil WS for modqueue decisions.")
                    delay = 1
                    if on_connect:
                        await on_connect()
                    async for msg in ws:
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            data = msg.json()
                            if data.get("type") == "modqueue.decision":
                                d = data.get("data", {})
                                await on_decision(
                                    d.get("message_id", ""),
                                    d.get("decision", ""),
                                    d.get("platform", "twitch"),
                                )
                        elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                            break
        except Exception:
            log.warning("Veil WS disconnected. Reconnecting in %ds.", delay, exc_info=True)
        await asyncio.sleep(delay)
        delay = min(delay * 2, 30)
