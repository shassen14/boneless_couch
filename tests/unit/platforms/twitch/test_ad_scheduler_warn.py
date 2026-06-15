# tests/unit/platforms/twitch/test_ad_scheduler_warn.py
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from couchd.platforms.twitch.ads.scheduler import AdScheduler

_MOD = "couchd.platforms.twitch.ads.scheduler"


@pytest.fixture
def ad_manager():
    m = MagicMock()
    m.log_ad = AsyncMock()
    m.required_seconds = 180
    return m


@pytest.fixture
def bot():
    b = MagicMock()
    user = MagicMock()
    user.start_commercial = AsyncMock()
    b.fetch_users = AsyncMock(return_value=[user])
    return b


@pytest.fixture
def scheduler(bot, ad_manager):
    return AdScheduler(bot=bot, ad_manager=ad_manager, youtube_client=None)


@pytest.fixture
def session():
    s = MagicMock()
    s.id = 1
    s.start_time = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    return s


# ── _start_commercial_with_retry ──────────────────────────────────────────────

async def test_retry_success_first_try(scheduler, bot):
    user = bot.fetch_users.return_value[0]
    with patch(f"{_MOD}.asyncio.sleep", AsyncMock()):
        ok = await scheduler._start_commercial_with_retry(user, 180)
    assert ok is True
    user.start_commercial.assert_awaited_once_with(length=180)


async def test_retry_eventually_succeeds(scheduler, bot):
    user = bot.fetch_users.return_value[0]
    user.start_commercial = AsyncMock(side_effect=[Exception("not live"), None])
    with patch(f"{_MOD}.asyncio.sleep", AsyncMock()):
        ok = await scheduler._start_commercial_with_retry(user, 180)
    assert ok is True
    assert user.start_commercial.await_count == 2


async def test_retry_gives_up_after_all_attempts(scheduler, bot):
    from couchd.core.constants import AdConfig
    user = bot.fetch_users.return_value[0]
    user.start_commercial = AsyncMock(side_effect=Exception("always fails"))
    with patch(f"{_MOD}.asyncio.sleep", AsyncMock()):
        ok = await scheduler._start_commercial_with_retry(user, 180)
    assert ok is False
    assert user.start_commercial.await_count == AdConfig.COMMERCIAL_RETRY_ATTEMPTS


# ── _warn_then_ad ─────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _no_sleep():
    with patch(f"{_MOD}.asyncio.sleep", AsyncMock()), \
         patch(f"{_MOD}.send_chat_message", AsyncMock()), \
         patch(f"{_MOD}.pick_ad_message", return_value=None), \
         patch(f"{_MOD}.pick_return_message", return_value="back!"), \
         patch(f"{_MOD}.clamp_to_ad_duration", side_effect=lambda s: s):
        yield


async def test_warn_then_ad_offline_skips(scheduler, bot, ad_manager, session):
    with patch(f"{_MOD}.get_active_session", AsyncMock(return_value=None)):
        await scheduler._warn_then_ad(session, 180)
    bot.fetch_users.assert_not_awaited()
    ad_manager.log_ad.assert_not_awaited()


async def test_warn_then_ad_logs_and_runs(scheduler, bot, ad_manager, session):
    user = bot.fetch_users.return_value[0]
    with patch(f"{_MOD}.get_active_session", AsyncMock(return_value=session)):
        await scheduler._warn_then_ad(session, 180, warn=False)
    user.start_commercial.assert_awaited_once_with(length=180)
    ad_manager.log_ad.assert_awaited_once()
    assert ad_manager.log_ad.call_args.args[0] == session.id
    assert ad_manager.log_ad.call_args.args[1] == 180


async def test_warn_then_ad_no_channel_user_aborts(scheduler, bot, ad_manager, session):
    bot.fetch_users = AsyncMock(return_value=[])
    with patch(f"{_MOD}.get_active_session", AsyncMock(return_value=session)):
        await scheduler._warn_then_ad(session, 180, warn=False)
    ad_manager.log_ad.assert_not_awaited()


async def test_warn_then_ad_commercial_failure_aborts(scheduler, bot, ad_manager, session):
    user = bot.fetch_users.return_value[0]
    user.start_commercial = AsyncMock(side_effect=Exception("nope"))
    with patch(f"{_MOD}.get_active_session", AsyncMock(return_value=session)):
        await scheduler._warn_then_ad(session, 180, warn=False)
    ad_manager.log_ad.assert_not_awaited()


async def test_warn_then_ad_resolves_session_when_none(scheduler, bot, ad_manager, session):
    # session passed as None → fetched after commercial fires.
    with patch(f"{_MOD}.get_active_session", AsyncMock(return_value=session)):
        await scheduler._warn_then_ad(None, 180, warn=False)
    ad_manager.log_ad.assert_awaited_once()
