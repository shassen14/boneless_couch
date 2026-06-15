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
