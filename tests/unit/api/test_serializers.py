# tests/unit/api/test_serializers.py
"""Pure serializer + route-parser tests (no DB, no HTTP)."""
from datetime import datetime, timedelta, timezone

from couchd.api import serializers
from couchd.api.routes import _parse_limit, _parse_since
from couchd.api.constants import ApiConfig, MarkerField, SessionField
from couchd.core.models import (
    ClipLog,
    ProblemAttempt,
    ProjectLog,
    StreamEvent,
    StreamSession,
)

START = datetime(2026, 4, 17, 21, 0, 0, tzinfo=timezone.utc)


def _session(**kw) -> StreamSession:
    return StreamSession(
        id=kw.get("id", 31),
        platform="twitch",
        title=kw.get("title", "LeetCode grind"),
        category="Software & Game Dev",
        vod_url=kw.get("vod_url", "https://twitch.tv/videos/123"),
        peak_viewers=47,
        start_time=START,
        end_time=kw.get("end_time", START + timedelta(seconds=7241)),
        is_active=False,
    )


def test_serialize_session_includes_vod_and_duration():
    data = serializers.serialize_session(_session())
    assert data[SessionField.VOD_URL.value] == "https://twitch.tv/videos/123"
    assert data[SessionField.DURATION_SECONDS.value] == 7241
    assert data[SessionField.START_TIME.value] == START.isoformat()


def test_duration_uses_now_when_session_still_live():
    data = serializers.serialize_session(_session(end_time=None))
    assert data[SessionField.DURATION_SECONDS.value] >= 0


def test_marker_absolute_seconds_is_offset_from_start():
    event = StreamEvent(
        id=412,
        event_type="problem_attempt",
        timestamp=START + timedelta(seconds=862),
        notes=None,
    )
    detail = ProblemAttempt(
        stream_event_id=412,
        slug="two-sum",
        title="Two Sum",
        difficulty="Easy",
        rating=1200,
        url="https://leetcode.com/problems/two-sum/",
        vod_timestamp="0:14:22",
    )
    marker = serializers.serialize_marker(event, START, detail)
    assert marker[MarkerField.ABSOLUTE_SECONDS.value] == 862
    assert marker[MarkerField.VOD_TIMESTAMP.value] == "0:14:22"
    assert marker[MarkerField.DETAIL.value]["slug"] == "two-sum"


def test_marker_clip_detail_shape():
    event = StreamEvent(id=423, event_type="clip", timestamp=START + timedelta(seconds=10))
    detail = ClipLog(
        stream_event_id=423,
        clip_id="AbcDef123",
        title="clean solve",
        url="https://clips.twitch.tv/AbcDef123",
        clipped_by="viewer42",
        platform="twitch",
    )
    marker = serializers.serialize_marker(event, START, detail)
    assert marker[MarkerField.DETAIL.value]["clip_id"] == "AbcDef123"


def test_marker_simple_event_has_null_detail_and_keeps_notes():
    event = StreamEvent(
        id=429,
        event_type="edit",
        timestamp=START + timedelta(seconds=5727),
        notes="thumbnail work",
    )
    marker = serializers.serialize_marker(event, START, None)
    assert marker[MarkerField.DETAIL.value] is None
    assert marker[MarkerField.NOTES.value] == "thumbnail work"
    assert marker[MarkerField.VOD_TIMESTAMP.value] is None
    assert marker[MarkerField.ABSOLUTE_SECONDS.value] == 5727


def test_serialize_recap_shape():
    recap = serializers.serialize_recap(
        _session(),
        problems=[{"title": "Two Sum"}],
        projects=[{"title": "boneless_couch"}],
        clip_count=3,
    )
    assert recap["clip_count"] == 3
    assert recap["problems"][0]["title"] == "Two Sum"


def test_parse_limit_clamps_and_defaults():
    assert _parse_limit(None) == ApiConfig.DEFAULT_SESSION_LIMIT
    assert _parse_limit("not-a-number") == ApiConfig.DEFAULT_SESSION_LIMIT
    assert _parse_limit("99999") == ApiConfig.MAX_SESSION_LIMIT
    assert _parse_limit("5") == 5


def test_parse_since_handles_z_suffix_and_bad_input():
    assert _parse_since(None) is None
    assert _parse_since("garbage") is None
    parsed = _parse_since("2026-04-17T21:00:00Z")
    assert parsed == START
