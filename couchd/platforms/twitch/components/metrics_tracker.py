# couchd/platforms/twitch/components/metrics_tracker.py
import logging
from collections import deque
from datetime import datetime, timezone, timedelta

from couchd.core.constants import ChatMetrics

log = logging.getLogger(__name__)


class ChatVelocityTracker:
    """Tracks chat message rate over a rolling time window."""

    def __init__(self):
        self._timestamps: deque[datetime] = deque()

    def record_message(self) -> None:
        """Record a chat message and prune entries outside the window."""
        now = datetime.now(timezone.utc)
        self._timestamps.append(now)
        cutoff = now - timedelta(minutes=ChatMetrics.VELOCITY_WINDOW_MINUTES)
        while self._timestamps and self._timestamps[0] < cutoff:
            self._timestamps.popleft()

    def get_rate_per_minute(self) -> float:
        """Return the average messages-per-minute over the velocity window."""
        return len(self._timestamps) / ChatMetrics.VELOCITY_WINDOW_MINUTES
