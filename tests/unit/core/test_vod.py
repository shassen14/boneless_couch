# tests/unit/core/test_vod.py
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

from couchd.core.constants import TwitchVodConfig
from couchd.core.vod import resolve_vod_url, select_vod_for_session

_UTC = timezone.utc
_START = datetime(2026, 9, 15, 19, 4, 19, tzinfo=_UTC)


def _video(vid: str, created: datetime) -> dict:
    return {
        "id": vid,
        "url": f"https://www.twitch.tv/videos/{vid}",
        "created_at": created.isoformat().replace("+00:00", "Z"),
    }


def test_matches_video_at_exact_start():
    videos = [_video("111", _START)]
    assert select_vod_for_session(videos, _START)["id"] == "111"


def test_picks_nearest_when_several_are_in_tolerance():
    videos = [
        _video("far", _START + timedelta(seconds=600)),
        _video("near", _START + timedelta(seconds=20)),
    ]
    assert select_vod_for_session(videos, _START)["id"] == "near"


def test_ignores_video_outside_tolerance():
    beyond = TwitchVodConfig.MATCH_TOLERANCE_SECONDS + 60
    videos = [_video("yesterday", _START + timedelta(seconds=beyond))]
    assert select_vod_for_session(videos, _START) is None


def test_matches_video_created_slightly_before_go_live():
    """Twitch's created_at can precede our EventSub timestamp by a few seconds."""
    videos = [_video("111", _START - timedelta(seconds=45))]
    assert select_vod_for_session(videos, _START)["id"] == "111"


def test_naive_start_time_treated_as_utc():
    videos = [_video("111", _START)]
    assert select_vod_for_session(videos, _START.replace(tzinfo=None))["id"] == "111"


def test_skips_videos_with_unparseable_created_at():
    videos = [{"id": "bad", "url": "u", "created_at": "not-a-date"}, _video("ok", _START)]
    assert select_vod_for_session(videos, _START)["id"] == "ok"


def test_empty_video_list_returns_none():
    assert select_vod_for_session([], _START) is None


async def test_resolve_vod_url_returns_matching_url():
    client = AsyncMock()
    client.get_user_id.return_value = "42"
    client.get_videos.return_value = [_video("111", _START)]
    url = await resolve_vod_url(client, "teststreamer", _START)
    assert url == "https://www.twitch.tv/videos/111"


async def test_resolve_vod_url_none_when_user_id_missing():
    client = AsyncMock()
    client.get_user_id.return_value = None
    assert await resolve_vod_url(client, "teststreamer", _START) is None
    client.get_videos.assert_not_awaited()


async def test_resolve_vod_url_none_when_no_videos():
    client = AsyncMock()
    client.get_user_id.return_value = "42"
    client.get_videos.return_value = []
    assert await resolve_vod_url(client, "teststreamer", _START) is None


async def test_resolve_vod_url_none_when_nothing_matches():
    client = AsyncMock()
    client.get_user_id.return_value = "42"
    stale = _START - timedelta(days=1)
    client.get_videos.return_value = [_video("old", stale)]
    assert await resolve_vod_url(client, "teststreamer", _START) is None
