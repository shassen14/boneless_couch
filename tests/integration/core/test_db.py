# tests/integration/core/test_db.py
#
# Tests get_active_session() against a real SQLite in-memory database.
# Patches couchd.core.utils.get_session with the test fixture.
from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from couchd.core.models import StreamSession
from couchd.core.utils import get_active_session

_PATCH = "couchd.core.utils.get_session"
_UTC = timezone.utc


async def test_get_active_session_returns_active_twitch_session(get_session_fn, db_session):
    obj = StreamSession(
        platform="twitch",
        is_active=True,
        start_time=datetime(2024, 1, 1, 12, 0, 0, tzinfo=_UTC),
    )
    db_session.add(obj)
    await db_session.commit()

    with patch(_PATCH, get_session_fn):
        result = await get_active_session()

    assert result is not None
    assert result.platform == "twitch"
    assert result.is_active is True


async def test_get_active_session_ignores_inactive_session(get_session_fn, db_session):
    obj = StreamSession(
        platform="twitch",
        is_active=False,
        start_time=datetime(2024, 1, 1, 12, 0, 0, tzinfo=_UTC),
    )
    db_session.add(obj)
    await db_session.commit()

    with patch(_PATCH, get_session_fn):
        result = await get_active_session()

    assert result is None


async def test_get_active_session_returns_most_recent_when_multiple(get_session_fn, db_session):
    older = StreamSession(
        platform="twitch",
        is_active=True,
        start_time=datetime(2024, 1, 1, 10, 0, 0, tzinfo=_UTC),
    )
    newer = StreamSession(
        platform="twitch",
        is_active=True,
        start_time=datetime(2024, 1, 1, 12, 0, 0, tzinfo=_UTC),
    )
    db_session.add(older)
    db_session.add(newer)
    await db_session.commit()
    await db_session.refresh(older)
    await db_session.refresh(newer)

    with patch(_PATCH, get_session_fn):
        result = await get_active_session()

    assert result is not None
    assert result.id == newer.id
