# couchd/api/serializers.py
"""Pure ORM -> dict conversion. No DB access, no ORM objects leak past here.

``absolute_seconds`` (event time minus session start) is the authoritative
DaVinci Resolve marker offset. ``vod_timestamp`` is human-readable and only set
when a chat command was run, so it is never relied on for positioning.
"""
from datetime import datetime, timezone

from couchd.core.models import (
    CFProblemAttempt,
    ClipLog,
    ProblemAttempt,
    ProjectLog,
    StreamEvent,
    StreamSession,
)
from couchd.api.constants import MarkerField, RecapField, SessionField


def _aware(dt: datetime | None) -> datetime | None:
    """Treat naive DB datetimes as UTC (defensive; columns are timezone=True)."""
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _iso(dt: datetime | None) -> str | None:
    aware = _aware(dt)
    return aware.isoformat() if aware else None


def duration_seconds(session: StreamSession) -> int | None:
    start = _aware(session.start_time)
    if start is None:
        return None
    end = _aware(session.end_time) or datetime.now(timezone.utc)
    return max(0, int((end - start).total_seconds()))


def serialize_session(session: StreamSession) -> dict:
    return {
        SessionField.ID.value: session.id,
        SessionField.PLATFORM.value: session.platform,
        SessionField.TITLE.value: session.title,
        SessionField.CATEGORY.value: session.category,
        SessionField.VOD_URL.value: session.vod_url,
        SessionField.PEAK_VIEWERS.value: session.peak_viewers,
        SessionField.START_TIME.value: _iso(session.start_time),
        SessionField.END_TIME.value: _iso(session.end_time),
        SessionField.DURATION_SECONDS.value: duration_seconds(session),
        SessionField.IS_ACTIVE.value: session.is_active,
    }


def _marker_detail(event_type: str, detail: object | None) -> dict | None:
    """Shape the per-event-type detail payload. Returns None for simple events."""
    if isinstance(detail, ProblemAttempt):
        return {
            "slug": detail.slug,
            "title": detail.title,
            "difficulty": detail.difficulty,
            "rating": detail.rating,
            "url": detail.url,
        }
    if isinstance(detail, CFProblemAttempt):
        return {
            "problem_id": detail.problem_id,
            "title": detail.title,
            "rating": detail.rating,
            "tags": detail.tags,
            "url": detail.url,
        }
    if isinstance(detail, ProjectLog):
        return {
            "title": detail.title,
            "url": detail.url,
            "description": detail.description,
        }
    if isinstance(detail, ClipLog):
        return {
            "clip_id": detail.clip_id,
            "title": detail.title,
            "url": detail.url,
            "clipped_by": detail.clipped_by,
        }
    return None


def serialize_marker(
    event: StreamEvent, start: datetime | None, detail: object | None
) -> dict:
    start_aware = _aware(start)
    ts = _aware(event.timestamp)
    absolute = (
        max(0, int((ts - start_aware).total_seconds()))
        if (ts and start_aware)
        else None
    )
    vod_timestamp = getattr(detail, "vod_timestamp", None)
    return {
        MarkerField.ID.value: event.id,
        MarkerField.EVENT_TYPE.value: event.event_type,
        MarkerField.TIMESTAMP.value: _iso(event.timestamp),
        MarkerField.VOD_TIMESTAMP.value: vod_timestamp,
        MarkerField.ABSOLUTE_SECONDS.value: absolute,
        MarkerField.NOTES.value: event.notes,
        MarkerField.DETAIL.value: _marker_detail(event.event_type, detail),
    }


def serialize_recap(
    session: StreamSession,
    problems: list[dict],
    projects: list[dict],
    clip_count: int,
) -> dict:
    return {
        RecapField.SESSION_ID.value: session.id,
        RecapField.TITLE.value: session.title,
        RecapField.DURATION_SECONDS.value: duration_seconds(session),
        RecapField.PEAK_VIEWERS.value: session.peak_viewers,
        RecapField.PROBLEMS.value: problems,
        RecapField.PROJECTS.value: projects,
        RecapField.CLIP_COUNT.value: clip_count,
    }
