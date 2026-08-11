# tests/unit/platforms/twitch/test_follow_alerts.py
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from couchd.core.constants import InteractionType
from couchd.core.models import ViewerInteraction
from couchd.platforms.twitch.main import TwitchBot

_MOD = "couchd.platforms.twitch.main"


def _payload(name="couchster"):
    return SimpleNamespace(
        user=SimpleNamespace(name=name, display_name=name.capitalize()),
        followed_at=datetime(2026, 6, 15, tzinfo=timezone.utc),
    )


def _db(prior_follow_id):
    """Async session whose first-follow lookup resolves to prior_follow_id (None = new)."""
    db = MagicMock()
    db.execute = AsyncMock(
        return_value=SimpleNamespace(scalar_one_or_none=lambda: prior_follow_id)
    )
    return db


@asynccontextmanager
async def _noop_session():
    yield MagicMock()


def _patches(db):
    @asynccontextmanager
    async def _gs():
        yield db

    return (
        patch(f"{_MOD}.get_session", _gs),
        patch(f"{_MOD}.get_active_session", new=AsyncMock(return_value=SimpleNamespace(id=7))),
        patch(f"{_MOD}.send_chat_message", new=AsyncMock()),
        patch(f"{_MOD}.veil.post_event", new=AsyncMock()),
    )


async def test_new_follower_alerts_and_logs():
    db = _db(prior_follow_id=None)
    gs, gas, send, post = _patches(db)
    with gs, gas, send as send_mock, post as post_mock:
        await TwitchBot.event_follow(MagicMock(), _payload())

    send_mock.assert_awaited_once()
    post_mock.assert_awaited_once()
    db.add.assert_called_once()


async def test_refollow_is_silent_but_still_logged():
    """A viewer who unfollowed and came back must not re-trigger the new-follower alert."""
    db = _db(prior_follow_id=42)
    gs, gas, send, post = _patches(db)
    with gs, gas, send as send_mock, post as post_mock:
        await TwitchBot.event_follow(MagicMock(), _payload())

    send_mock.assert_not_awaited()
    post_mock.assert_not_awaited()
    db.add.assert_called_once()

    row = db.add.call_args[0][0]
    assert isinstance(row, ViewerInteraction)
    assert row.interaction_type == InteractionType.FOLLOW
    assert row.username == "couchster"
