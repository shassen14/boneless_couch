# tests/unit/core/test_utils.py
from datetime import datetime, timezone
from unittest.mock import patch

from couchd.core.utils import compute_vod_timestamp

_UTC = timezone.utc


def _now(dt: datetime):
    return patch("couchd.core.utils.datetime")


async def test_compute_vod_timestamp_basic():
    start = datetime(2024, 1, 1, 10, 29, 15, tzinfo=_UTC)
    now = datetime(2024, 1, 1, 12, 0, 0, tzinfo=_UTC)  # 1h 30m 45s later
    with patch("couchd.core.utils.datetime") as mock_dt:
        mock_dt.now.return_value = now
        result = compute_vod_timestamp(start)
    assert result == "01h30m45s"


async def test_compute_vod_timestamp_naive_start_treated_as_utc():
    start = datetime(2024, 1, 1, 10, 0, 0)  # naive — no tzinfo
    now = datetime(2024, 1, 1, 11, 0, 0, tzinfo=_UTC)  # 1h later
    with patch("couchd.core.utils.datetime") as mock_dt:
        mock_dt.now.return_value = now
        result = compute_vod_timestamp(start)
    assert result == "01h00m00s"


async def test_compute_vod_timestamp_zero():
    ts = datetime(2024, 1, 1, 12, 0, 0, tzinfo=_UTC)
    with patch("couchd.core.utils.datetime") as mock_dt:
        mock_dt.now.return_value = ts
        result = compute_vod_timestamp(ts)
    assert result == "00h00m00s"
