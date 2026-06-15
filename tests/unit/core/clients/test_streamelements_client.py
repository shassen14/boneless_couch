# tests/unit/core/clients/test_streamelements_client.py
import json
from unittest.mock import AsyncMock, patch

from couchd.core.clients import streamelements


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
