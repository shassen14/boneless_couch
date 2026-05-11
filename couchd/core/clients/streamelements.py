# couchd/core/clients/streamelements.py
import asyncio
import json
import logging
from collections.abc import Callable, Awaitable

import aiohttp

from couchd.core.config import settings

log = logging.getLogger(__name__)

_SE_WS_URL = "wss://realtime.streamelements.com/socket.io/?EIO=4&transport=websocket"


async def listen_tips(on_tip: Callable[[dict], Awaitable[None]]) -> None:
    """Connect to StreamElements Socket.IO and call on_tip(data) for each tip event."""
    if not settings.STREAMELEMENTS_JWT:
        return
    delay = 1
    while True:
        try:
            async with aiohttp.ClientSession() as http:
                async with http.ws_connect(_SE_WS_URL) as ws:
                    log.info("Connected to StreamElements WebSocket.")
                    delay = 1
                    async for msg in ws:
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            await _handle(ws, msg.data, on_tip)
                        elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                            break
        except aiohttp.ClientConnectorError:
            log.warning("StreamElements WS unreachable. Reconnecting in %ds.", delay)
        except Exception:
            log.warning("StreamElements WS error. Reconnecting in %ds.", delay, exc_info=True)
        await asyncio.sleep(delay)
        delay = min(delay * 2, 60)


async def _handle(
    ws: aiohttp.ClientWebSocketResponse,
    data: str,
    on_tip: Callable[[dict], Awaitable[None]],
) -> None:
    # Engine.IO OPEN — server ready, initiate Socket.IO connect
    if data.startswith("0"):
        await ws.send_str("40")
        return

    # Engine.IO PING — keep connection alive
    if data == "2":
        await ws.send_str("3")
        return

    # Socket.IO packets start with "4"
    if not data.startswith("4"):
        return

    eio_type = data[1] if len(data) > 1 else ""

    # Socket.IO CONNECT ack — authenticate
    if eio_type == "0":
        payload = json.dumps({"method": "jwt", "token": settings.STREAMELEMENTS_JWT})
        await ws.send_str(f'42["authenticate",{payload}]')
        return

    # Socket.IO EVENT
    if eio_type == "2":
        try:
            packet = json.loads(data[2:])
        except (json.JSONDecodeError, IndexError):
            return
        event_name = packet[0] if packet else None
        if event_name == "authenticated":
            log.info("StreamElements authenticated successfully.")
        elif event_name == "unauthorized":
            log.error("StreamElements JWT rejected — check STREAMELEMENTS_JWT in .env.")
        elif event_name == "event" and len(packet) > 1:
            event_data = packet[1]
            if event_data.get("type") == "tip":
                await on_tip(event_data.get("data", {}))
