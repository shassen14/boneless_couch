# tests/integration/api/test_queries.py
"""Query-layer tests against an in-memory SQLite DB.

``couchd.api.queries`` imports ``get_session`` at module scope, so we monkeypatch
that reference to the test engine's session factory.
"""
from datetime import datetime, timedelta, timezone

import pytest

from couchd.api import queries
from couchd.core.models import (
    ClipLog,
    ProblemAttempt,
    ProjectLog,
    StreamEvent,
    StreamSession,
)

START = datetime(2026, 4, 17, 21, 0, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def _patch_get_session(monkeypatch, get_session_fn):
    monkeypatch.setattr(queries, "get_session", get_session_fn)


@pytest.fixture
async def seeded(db_session):
    session = StreamSession(
        platform="twitch",
        title="grind",
        vod_url="https://twitch.tv/videos/99",
        start_time=START,
        end_time=START + timedelta(seconds=3600),
        is_active=False,
        peak_viewers=12,
    )
    db_session.add(session)
    await db_session.flush()

    problem_event = StreamEvent(
        session_id=session.id,
        event_type="problem_attempt",
        timestamp=START + timedelta(seconds=100),
    )
    project_event = StreamEvent(
        session_id=session.id,
        event_type="project",
        timestamp=START + timedelta(seconds=200),
    )
    clip_event = StreamEvent(
        session_id=session.id,
        event_type="clip",
        timestamp=START + timedelta(seconds=300),
    )
    edit_event = StreamEvent(
        session_id=session.id,
        event_type="edit",
        timestamp=START + timedelta(seconds=400),
        notes="thumbnail",
    )
    db_session.add_all([problem_event, project_event, clip_event, edit_event])
    await db_session.flush()

    db_session.add_all(
        [
            ProblemAttempt(
                stream_event_id=problem_event.id,
                slug="two-sum",
                title="Two Sum",
                difficulty="Easy",
                rating=1200,
                url="https://leetcode.com/problems/two-sum/",
                vod_timestamp="0:01:40",
            ),
            ProjectLog(
                stream_event_id=project_event.id,
                title="boneless_couch",
                url="https://github.com/x/y",
            ),
            ClipLog(
                stream_event_id=clip_event.id,
                clip_id="C1",
                title="nice",
                url="https://clips.twitch.tv/C1",
                platform="twitch",
            ),
        ]
    )
    await db_session.commit()
    return session


async def test_list_sessions_returns_serialized(seeded):
    rows = await queries.list_sessions(since=None, limit=50)
    assert len(rows) == 1
    assert rows[0]["vod_url"] == "https://twitch.tv/videos/99"


async def test_get_markers_orders_and_maps_all_extension_tables(seeded):
    markers = await queries.get_markers(seeded.id)
    assert [m["event_type"] for m in markers] == [
        "problem_attempt",
        "project",
        "clip",
        "edit",
    ]
    assert [m["absolute_seconds"] for m in markers] == [100, 200, 300, 400]
    assert markers[0]["detail"]["slug"] == "two-sum"
    assert markers[2]["detail"]["clip_id"] == "C1"
    assert markers[3]["detail"] is None
    assert markers[3]["notes"] == "thumbnail"


async def test_get_markers_unknown_session_returns_none(seeded):
    assert await queries.get_markers(999999) is None


async def test_get_recap_counts_and_lists(seeded):
    recap = await queries.get_recap(seeded.id)
    assert recap["clip_count"] == 1
    assert recap["problems"][0]["title"] == "Two Sum"
    assert recap["projects"][0]["title"] == "boneless_couch"
    assert recap["duration_seconds"] == 3600


async def test_get_recap_unknown_session_returns_none(seeded):
    assert await queries.get_recap(999999) is None


async def test_get_session_detail_round_trips(seeded):
    detail = await queries.get_session_detail(seeded.id)
    assert detail["id"] == seeded.id
    assert detail["title"] == "grind"


async def test_get_session_detail_unknown_returns_none(seeded):
    assert await queries.get_session_detail(999999) is None


async def test_list_sessions_since_filters_out_older(seeded):
    after_end = START + timedelta(seconds=7200)
    assert await queries.list_sessions(since=after_end, limit=50) == []
    assert len(await queries.list_sessions(since=START, limit=50)) == 1


async def test_list_sessions_limit_caps_rows(db_session):
    for i in range(3):
        db_session.add(
            StreamSession(
                platform="twitch",
                title=f"s{i}",
                start_time=START + timedelta(hours=i),
                is_active=False,
            )
        )
    await db_session.commit()
    rows = await queries.list_sessions(since=None, limit=2)
    assert len(rows) == 2
    # Newest first: ordered by start_time desc.
    assert rows[0]["title"] == "s2"


async def test_get_active_session_returns_active_twitch_only(db_session):
    inactive = StreamSession(
        platform="twitch", title="old", start_time=START, is_active=False
    )
    other_platform = StreamSession(
        platform="youtube",
        title="yt",
        start_time=START + timedelta(hours=1),
        is_active=True,
    )
    active = StreamSession(
        platform="twitch",
        title="live",
        start_time=START + timedelta(hours=2),
        is_active=True,
    )
    db_session.add_all([inactive, other_platform, active])
    await db_session.commit()

    data = await queries.get_active_session()
    assert data is not None
    assert data["title"] == "live"


async def test_get_active_session_none_when_no_active(db_session):
    db_session.add(
        StreamSession(
            platform="twitch", title="old", start_time=START, is_active=False
        )
    )
    await db_session.commit()
    assert await queries.get_active_session() is None
