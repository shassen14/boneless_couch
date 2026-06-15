# tests/unit/core/test_utils.py
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from couchd.core.constants import InteractionType, Platform
from couchd.core.models import StreamSession, ViewerInteraction
from couchd.core.utils import compute_vod_timestamp, get_active_session, get_overlay_stats

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


# ── get_active_session ───────────────────────────────────────────────────────

async def test_get_active_session_returns_latest_active_for_platform(db_session, get_session_fn):
    db_session.add_all([
        StreamSession(platform="twitch", is_active=False,
                      start_time=datetime(2024, 1, 1, tzinfo=_UTC)),
        StreamSession(platform="twitch", is_active=True,
                      start_time=datetime(2024, 1, 2, tzinfo=_UTC)),
        StreamSession(platform="twitch", is_active=True,
                      start_time=datetime(2024, 1, 3, tzinfo=_UTC)),  # newest
        StreamSession(platform="youtube", is_active=True,
                      start_time=datetime(2024, 1, 4, tzinfo=_UTC)),
    ])
    await db_session.commit()

    with patch("couchd.core.utils.get_session", get_session_fn):
        result = await get_active_session(Platform.TWITCH)

    assert result is not None
    assert result.platform == "twitch"
    assert result.start_time.day == 3


async def test_get_active_session_none_when_no_active(db_session, get_session_fn):
    db_session.add(StreamSession(platform="twitch", is_active=False,
                                 start_time=datetime(2024, 1, 1, tzinfo=_UTC)))
    await db_session.commit()

    with patch("couchd.core.utils.get_session", get_session_fn):
        result = await get_active_session(Platform.TWITCH)

    assert result is None


# ── get_overlay_stats ────────────────────────────────────────────────────────

def _vi(interaction_type, username, **kw):
    base = dict(
        interaction_type=interaction_type,
        username=username,
        display_name=username.title(),
        timestamp=kw.pop("timestamp", datetime(2024, 1, 1, tzinfo=_UTC)),
    )
    base.update(kw)
    return ViewerInteraction(**base)


async def test_get_overlay_stats_empty(get_session_fn):
    with patch("couchd.core.utils.get_session", get_session_fn):
        stats = await get_overlay_stats()
    assert stats == {
        "last_follower": {},
        "last_raider": {},
        "last_bits": {},
        "recent_subs": [],
        "longest_subs": [],
    }


async def test_get_overlay_stats_picks_most_recent_per_type(db_session, get_session_fn):
    t0 = datetime(2024, 1, 1, tzinfo=_UTC)
    db_session.add_all([
        _vi(InteractionType.FOLLOW, "early_follow", timestamp=t0),
        _vi(InteractionType.FOLLOW, "late_follow", timestamp=t0 + timedelta(hours=1)),
        _vi(InteractionType.RAID, "raider1", viewer_count=20, timestamp=t0),
        _vi(InteractionType.BITS, "cheerer", bits=100, timestamp=t0),
    ])
    await db_session.commit()

    with patch("couchd.core.utils.get_session", get_session_fn):
        stats = await get_overlay_stats()

    assert stats["last_follower"]["username"] == "late_follow"
    assert stats["last_raider"]["username"] == "raider1"
    assert stats["last_bits"]["bits"] == 100


async def test_get_overlay_stats_longest_subs_excludes_broadcaster_and_ranks(db_session, get_session_fn):
    t0 = datetime(2024, 1, 1, tzinfo=_UTC)
    rows = []
    # loyal: 3 subs, casual: 1 sub, broadcaster (teststreamer): 5 subs but excluded
    for i in range(3):
        rows.append(_vi(InteractionType.SUB, "loyal", timestamp=t0 + timedelta(minutes=i)))
    rows.append(_vi(InteractionType.RESUB, "casual", timestamp=t0))
    for i in range(5):
        rows.append(_vi(InteractionType.SUB, "teststreamer", timestamp=t0 + timedelta(seconds=i)))
    db_session.add_all(rows)
    await db_session.commit()

    with patch("couchd.core.utils.get_session", get_session_fn):
        stats = await get_overlay_stats()

    longest = stats["longest_subs"]
    names = [r["username"] for r in longest]
    assert "teststreamer" not in names
    assert longest[0]["username"] == "loyal"
    assert longest[0]["cumulative_months"] == 3
