# tests/unit/core/clients/test_streamelements_client.py
import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest

from couchd.core.clients import streamelements

_MOD = "couchd.core.clients.streamelements"


class _FakeWS:
    def __init__(self):
        self.sent: list[str] = []

    async def send_str(self, data: str):
        self.sent.append(data)


async def _handle(data: str, on_tip=None, jwt="test-jwt"):
    ws = _FakeWS()
    on_tip = on_tip or AsyncMock()
    with patch.object(streamelements.settings, "STREAMELEMENTS_JWT", jwt):
        await streamelements._handle(ws, data, on_tip)
    return ws, on_tip


async def test_engineio_open_initiates_socketio_connect():
    ws, _ = await _handle("0{\"sid\":\"x\"}")
    assert ws.sent == ["40"]


async def test_engineio_ping_replies_pong():
    ws, _ = await _handle("2")
    assert ws.sent == ["3"]


async def test_socketio_connect_ack_authenticates_with_jwt():
    ws, _ = await _handle("40", jwt="my-secret-jwt")
    assert len(ws.sent) == 1
    assert ws.sent[0].startswith("42[\"authenticate\",")
    payload = json.loads(ws.sent[0][len("42[\"authenticate\","):-1])
    assert payload == {"method": "jwt", "token": "my-secret-jwt"}


async def test_tip_event_invokes_callback_with_data():
    on_tip = AsyncMock()
    tip_data = {"username": "gen", "amount": 5.0, "currency": "USD"}
    packet = json.dumps(["event", {"type": "tip", "data": tip_data}])
    await _handle("42" + packet, on_tip=on_tip)
    on_tip.assert_awaited_once_with(tip_data)


async def test_non_tip_event_ignored():
    on_tip = AsyncMock()
    packet = json.dumps(["event", {"type": "follow", "data": {}}])
    await _handle("42" + packet, on_tip=on_tip)
    on_tip.assert_not_awaited()


async def test_authenticated_event_no_callback_no_send():
    on_tip = AsyncMock()
    ws, _ = await _handle("42" + json.dumps(["authenticated", {}]), on_tip=on_tip)
    on_tip.assert_not_awaited()
    assert ws.sent == []


async def test_unauthorized_event_no_callback():
    on_tip = AsyncMock()
    await _handle("42" + json.dumps(["unauthorized", {}]), on_tip=on_tip)
    on_tip.assert_not_awaited()


async def test_malformed_event_json_is_swallowed():
    on_tip = AsyncMock()
    ws, _ = await _handle("42[not valid json", on_tip=on_tip)
    on_tip.assert_not_awaited()
    assert ws.sent == []


async def test_unknown_non_socketio_message_ignored():
    on_tip = AsyncMock()
    ws, _ = await _handle("9garbage", on_tip=on_tip)
    on_tip.assert_not_awaited()
    assert ws.sent == []


async def test_event_packet_without_data_is_ignored():
    on_tip = AsyncMock()
    # eio EVENT with only the name, no payload element.
    await _handle("42" + json.dumps(["event"]), on_tip=on_tip)
    on_tip.assert_not_awaited()


# ── listen_tips connection loop ───────────────────────────────────────────────


class _LoopWS:
    def __init__(self, messages):
        self._messages = messages
        self.sent: list[str] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def send_str(self, data):
        self.sent.append(data)

    def __aiter__(self):
        self._it = iter(self._messages)
        return self

    async def __anext__(self):
        try:
            return next(self._it)
        except StopIteration:
            raise StopAsyncIteration


class _LoopMsg:
    def __init__(self, type_, data=None):
        self.type = type_
        self.data = data


def _ws_session(ws):
    http = MagicMock()
    http.ws_connect = MagicMock(return_value=ws)
    session_cm = AsyncMock()
    session_cm.__aenter__ = AsyncMock(return_value=http)
    session_cm.__aexit__ = AsyncMock(return_value=False)
    return MagicMock(return_value=session_cm)


async def test_listen_tips_no_jwt_is_noop():
    on_tip = AsyncMock()
    with patch.object(streamelements.settings, "STREAMELEMENTS_JWT", None):
        await streamelements.listen_tips(on_tip)
    on_tip.assert_not_awaited()


async def test_listen_tips_dispatches_text_to_handler_and_breaks_on_close():
    on_tip = AsyncMock()
    tip = {"username": "gen", "amount": 5.0}
    messages = [
        _LoopMsg(aiohttp.WSMsgType.TEXT, "0{}"),  # engine.io OPEN → "40"
        _LoopMsg(aiohttp.WSMsgType.TEXT, "42" + json.dumps(["event", {"type": "tip", "data": tip}])),
        _LoopMsg(aiohttp.WSMsgType.CLOSED),
    ]
    ws = _LoopWS(messages)
    with patch.object(streamelements.settings, "STREAMELEMENTS_JWT", "jwt"), patch(
        "aiohttp.ClientSession", _ws_session(ws)
    ), patch(f"{_MOD}.asyncio.sleep", AsyncMock(side_effect=asyncio.CancelledError)):
        with pytest.raises(asyncio.CancelledError):
            await streamelements.listen_tips(on_tip)

    assert ws.sent[0] == "40"  # responded to engine.io OPEN
    on_tip.assert_awaited_once_with(tip)
