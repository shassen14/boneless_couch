# tests/unit/platforms/twitch/test_metrics_tracker.py
from datetime import datetime, timedelta, timezone

from couchd.core.constants import ChatMetrics
from couchd.platforms.twitch.components.metrics_tracker import ChatVelocityTracker


def test_empty_tracker_rate_is_zero():
    assert ChatVelocityTracker().get_rate_per_minute() == 0.0


def test_rate_is_count_over_window():
    tracker = ChatVelocityTracker()
    for _ in range(ChatMetrics.VELOCITY_WINDOW_MINUTES * 5):
        tracker.record_message()
    # count / window_minutes
    assert tracker.get_rate_per_minute() == 5.0


def test_old_messages_are_pruned():
    tracker = ChatVelocityTracker()
    # Inject a message older than the window, then record a fresh one.
    stale = datetime.now(timezone.utc) - timedelta(
        minutes=ChatMetrics.VELOCITY_WINDOW_MINUTES + 1
    )
    tracker._timestamps.append(stale)

    tracker.record_message()

    # Stale entry dropped; only the fresh message remains.
    assert len(tracker._timestamps) == 1
