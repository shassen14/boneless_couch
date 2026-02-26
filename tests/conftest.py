# tests/conftest.py
#
# Module-level sys.modules patch runs during collection, before any test file
# imports couchd modules, so config.py's FileNotFoundError is never triggered.
import sys
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# ── Patch settings before any couchd import ──────────────────────────────────
_mock_settings = MagicMock()
_mock_settings.TWITCH_CHANNEL = "teststreamer"
_mock_settings.LEETCODE_USERNAME = "testlcuser"
_mock_settings.TWITCH_BOT_ID = "12345"
_mock_settings.DB_USER = "test"
_mock_settings.DB_PASSWORD = "test"
_mock_settings.DB_HOST = "localhost"
_mock_settings.DB_PORT = 5432
_mock_settings.DB_NAME = "test"

_config_mod = MagicMock()
_config_mod.settings = _mock_settings
sys.modules["couchd.core.config"] = _config_mod

# ── Safe to import couchd after the patch ────────────────────────────────────
from couchd.core.db import Base  # noqa: E402
from couchd.core.models import StreamEvent, StreamSession  # noqa: E402


@pytest.fixture
def mock_settings():
    return _mock_settings


# ── SQLite in-memory DB fixtures (integration tests) ─────────────────────────

@pytest.fixture
async def db_engine():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest.fixture
async def db_session(db_engine):
    factory = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)
    async with factory() as session:
        yield session


@pytest.fixture
def get_session_fn(db_engine):
    """Returns a get_session replacement that uses the test SQLite engine."""
    factory = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)

    @asynccontextmanager
    async def _get_session():
        async with factory() as session:
            yield session

    return _get_session


@pytest.fixture
async def stream_session(db_session):
    obj = StreamSession(
        platform="twitch",
        is_active=True,
        start_time=datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
    )
    db_session.add(obj)
    await db_session.commit()
    await db_session.refresh(obj)
    return obj


@pytest.fixture
async def lc_event(db_session, stream_session):
    obj = StreamEvent(
        session_id=stream_session.id,
        event_type="leetcode",
        title="1. Two Sum",
        url="https://leetcode.com/problems/two-sum/",
        platform_id="two-sum",
        status="Easy",
        rating=1200,
        vod_timestamp="00h10m00s",
    )
    db_session.add(obj)
    await db_session.commit()
    await db_session.refresh(obj)
    return obj
