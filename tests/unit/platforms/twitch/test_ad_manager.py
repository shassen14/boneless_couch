# tests/unit/platforms/twitch/test_ad_manager.py
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from couchd.platforms.twitch.ads.manager import AdBudgetManager

_GET_SESSION = "couchd.platforms.twitch.ads.manager.get_session"


@pytest.fixture
def manager():
    return AdBudgetManager(required_minutes=3)  # 180s budget, 3780s window


def test_window_includes_post_ad_cooldown(manager):
    # Twitch's 60-min cooldown starts after the ad ends → window = 3600 + budget.
    assert manager.window_seconds == 3600 + 180


def test_required_seconds_property(manager):
    assert manager.required_seconds == 180


def test_fire_threshold_below_full_budget_and_matches_formula(manager):
    # Threshold is the budget level once nearly the whole window has elapsed,
    # so it must be just under the full budget.
    req, window = 180, 3780
    assert manager.fire_threshold == pytest.approx(req * window / (window + req))
    assert manager.fire_threshold < manager.required_seconds


def test_set_pending_tracks_task(manager):
    task = MagicMock()
    task.done.return_value = False
    manager.set_pending(task)
    assert manager.has_pending() is True


# ── get_remaining accumulation math ───────────────────────────────────────────

async def test_remaining_full_after_full_window(manager):
    manager.get_last_ad_time = AsyncMock(return_value=None)
    start = datetime.now(timezone.utc) - timedelta(seconds=manager.window_seconds * 2)

    # Elapsed is capped at the window, so the whole budget has accrued.
    assert await manager.get_remaining(1, start) == 180


async def test_remaining_proportional_midway(manager):
    manager.get_last_ad_time = AsyncMock(return_value=None)
    start = datetime.now(timezone.utc) - timedelta(seconds=manager.window_seconds // 2)

    remaining = await manager.get_remaining(1, start)
    assert abs(remaining - 90) <= 1  # ~half the budget, allow sub-second drift


async def test_remaining_uses_last_ad_over_start(manager):
    # A recent ad resets accrual even if the stream started long ago.
    recent_ad = datetime.now(timezone.utc) - timedelta(seconds=0)
    manager.get_last_ad_time = AsyncMock(return_value=recent_ad)
    old_start = datetime.now(timezone.utc) - timedelta(hours=5)

    assert await manager.get_remaining(1, old_start) == 0


async def test_remaining_handles_naive_reference(manager):
    # get_last_ad_time may return a tz-naive datetime; must not raise.
    aware = datetime.now(timezone.utc) - timedelta(seconds=manager.window_seconds)
    naive = aware.replace(tzinfo=None)
    manager.get_last_ad_time = AsyncMock(return_value=naive)

    assert await manager.get_remaining(1, datetime.now(timezone.utc)) == 180


# ── pending task tracking ─────────────────────────────────────────────────────

def test_has_pending_false_when_none(manager):
    assert manager.has_pending() is False


def test_has_pending_true_for_running_task(manager):
    task = MagicMock()
    task.done.return_value = False
    manager._pending_task = task
    assert manager.has_pending() is True


def test_has_pending_false_for_done_task(manager):
    task = MagicMock()
    task.done.return_value = True
    manager._pending_task = task
    assert manager.has_pending() is False


def test_cancel_pending_cancels_running_task(manager):
    task = MagicMock()
    task.done.return_value = False
    manager._pending_task = task

    manager.cancel_pending()

    task.cancel.assert_called_once()
    assert manager._pending_task is None


# ── log_ad / get_last_ad_time DB roundtrip ────────────────────────────────────

async def test_log_ad_then_get_last_ad_time(manager, get_session_fn, stream_session):
    with patch(_GET_SESSION, get_session_fn):
        assert await manager.get_last_ad_time(stream_session.id) is None

        await manager.log_ad(stream_session.id, 90, "00h30m00s")

        last = await manager.get_last_ad_time(stream_session.id)

    assert last is not None
