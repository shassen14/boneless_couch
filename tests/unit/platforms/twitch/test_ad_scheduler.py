# tests/unit/platforms/twitch/test_ad_scheduler.py
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from couchd.core.constants import AdConfig
from couchd.platforms.twitch.ads.scheduler import AdScheduler
from couchd.platforms.twitch.components.utils import clamp_to_ad_duration

_SLEEP = "couchd.platforms.twitch.ads.scheduler.asyncio.sleep"


@pytest.fixture
def scheduler():
    return AdScheduler(bot=MagicMock(), ad_manager=MagicMock(), youtube_client=None)


# ── _start_commercial_with_retry ──────────────────────────────────────────────

async def test_start_commercial_succeeds_first_try(scheduler):
    user = MagicMock()
    user.start_commercial = AsyncMock()

    with patch(_SLEEP, AsyncMock()) as sleep:
        ok = await scheduler._start_commercial_with_retry(user, 60)

    assert ok is True
    user.start_commercial.assert_awaited_once_with(length=60)
    sleep.assert_not_called()


async def test_start_commercial_retries_then_succeeds(scheduler):
    user = MagicMock()
    # Twitch rejects twice ("not live yet"), then accepts.
    user.start_commercial = AsyncMock(side_effect=[Exception("not live"), Exception("not live"), None])

    with patch(_SLEEP, AsyncMock()) as sleep:
        ok = await scheduler._start_commercial_with_retry(user, 90)

    assert ok is True
    assert user.start_commercial.await_count == 3
    assert sleep.await_count == 2


async def test_start_commercial_gives_up_after_max_attempts(scheduler):
    user = MagicMock()
    user.start_commercial = AsyncMock(side_effect=Exception("never live"))

    with patch(_SLEEP, AsyncMock()):
        ok = await scheduler._start_commercial_with_retry(user, 120)

    assert ok is False
    assert user.start_commercial.await_count == AdConfig.COMMERCIAL_RETRY_ATTEMPTS


# ── clamp_to_ad_duration ──────────────────────────────────────────────────────

@pytest.mark.parametrize("seconds,expected", [
    (30, 30),
    (45, 30),
    (60, 60),
    (89, 60),
    (180, 180),
    (999, 180),   # caps at the largest valid duration
    (0, 30),      # floors at the smallest valid duration
])
def test_clamp_to_ad_duration(seconds, expected):
    assert clamp_to_ad_duration(seconds) == expected


# ── fire_opener ───────────────────────────────────────────────────────────────

def test_fire_opener_skips_when_already_pending(scheduler):
    scheduler._ad_manager.has_pending.return_value = True

    with patch("couchd.platforms.twitch.ads.scheduler.asyncio.create_task") as ct:
        scheduler.fire_opener()

    ct.assert_not_called()
    scheduler._ad_manager.set_pending.assert_not_called()


def test_fire_opener_schedules_via_public_api(scheduler):
    scheduler._ad_manager.has_pending.return_value = False
    scheduler._ad_manager.required_seconds = 180

    sentinel = object()
    with patch.object(scheduler, "_warn_then_ad", MagicMock()), \
         patch("couchd.platforms.twitch.ads.scheduler.asyncio.create_task", return_value=sentinel) as ct:
        scheduler.fire_opener()

    ct.assert_called_once()
    # Task is registered through the manager's public API, not by poking privates.
    scheduler._ad_manager.set_pending.assert_called_once_with(sentinel)


# ── _warn_then_ad safety net ──────────────────────────────────────────────────

_GAS = "couchd.platforms.twitch.ads.scheduler.get_active_session"


async def test_warn_then_ad_skips_when_stream_offline(scheduler):
    scheduler._bot.fetch_users = AsyncMock()

    with patch(_SLEEP, AsyncMock()), \
         patch(_GAS, AsyncMock(return_value=None)), \
         patch("couchd.platforms.twitch.ads.scheduler.send_chat_message", AsyncMock()):
        await scheduler._warn_then_ad(None, 180, warn=False)

    # Went offline before firing: never tries to start a commercial.
    scheduler._bot.fetch_users.assert_not_called()


async def test_warn_then_ad_aborts_when_no_channel_user(scheduler):
    scheduler._bot.fetch_users = AsyncMock(return_value=[])
    session = MagicMock()

    with patch(_SLEEP, AsyncMock()), \
         patch(_GAS, AsyncMock(return_value=session)), \
         patch("couchd.platforms.twitch.ads.scheduler.send_chat_message", AsyncMock()), \
         patch("couchd.platforms.twitch.ads.scheduler.clamp_to_ad_duration", return_value=180), \
         patch.object(scheduler, "_start_commercial_with_retry", AsyncMock()) as start:
        await scheduler._warn_then_ad(session, 180, warn=False)

    start.assert_not_called()
    scheduler._ad_manager.log_ad.assert_not_called()
