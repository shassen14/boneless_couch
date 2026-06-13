# tests/unit/core/test_content_os_client.py
"""Outbound content_os notification client: disabled-by-default + request shape."""
from contextlib import asynccontextmanager
from unittest.mock import MagicMock

import pytest

from couchd.core.clients import content_os as client


class _FakeResp:
    def __init__(self, status=202):
        self.status = status

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class _FakeSession:
    """Records the single POST call so tests can assert URL/headers/body."""

    last_call: dict = {}

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def post(self, url, json=None, headers=None, timeout=None):
        _FakeSession.last_call = {"url": url, "json": json, "headers": headers}
        return _FakeResp()


@pytest.fixture
def fake_aiohttp(monkeypatch):
    _FakeSession.last_call = {}
    fake = MagicMock()
    fake.ClientSession = _FakeSession
    fake.ClientTimeout = lambda total=None: total
    fake.ClientConnectorError = Exception
    monkeypatch.setattr(client, "aiohttp", fake)
    return fake


async def test_noop_when_url_unset(monkeypatch, fake_aiohttp):
    monkeypatch.setattr(client.settings, "CONTENT_OS_API_URL", None)
    await client.notify_session_end(31)
    assert _FakeSession.last_call == {}


async def test_posts_session_id_with_bearer(monkeypatch, fake_aiohttp):
    monkeypatch.setattr(client.settings, "CONTENT_OS_API_URL", "http://pi.local:8000")
    monkeypatch.setattr(client.settings, "CONTENT_OS_API_SECRET", "s3cret")
    await client.notify_session_end(31)
    call = _FakeSession.last_call
    assert call["url"] == "http://pi.local:8000/api/ingest/session-available"
    assert call["json"] == {"session_id": 31}
    assert call["headers"]["Authorization"] == "Bearer s3cret"
