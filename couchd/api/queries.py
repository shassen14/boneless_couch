# couchd/api/queries.py
"""Async DB reads for the content_os API. Returns serialized dicts only.

One module owns the SQL so routes stay thin and serializers stay pure.
"""
from datetime import datetime

from sqlalchemy import func, select

from couchd.core.db import get_session
from couchd.core.constants import Platform
from couchd.core.models import (
    CFProblemAttempt,
    ClipLog,
    ProblemAttempt,
    ProjectLog,
    StreamEvent,
    StreamSession,
)
from couchd.api import serializers


async def list_sessions(since: datetime | None, limit: int) -> list[dict]:
    async with get_session() as db:
        stmt = select(StreamSession).order_by(StreamSession.start_time.desc())
        if since is not None:
            stmt = stmt.where(StreamSession.start_time >= since)
        stmt = stmt.limit(limit)
        rows = (await db.execute(stmt)).scalars().all()
    return [serializers.serialize_session(s) for s in rows]


async def get_active_session() -> dict | None:
    async with get_session() as db:
        row = (
            await db.execute(
                select(StreamSession)
                .where(
                    (StreamSession.is_active == True)  # noqa: E712
                    & (StreamSession.platform == Platform.TWITCH.value)
                )
                .order_by(StreamSession.start_time.desc())
            )
        ).scalars().first()
    return serializers.serialize_session(row) if row else None


async def get_session_detail(session_id: int) -> dict | None:
    async with get_session() as db:
        row = await db.get(StreamSession, session_id)
    return serializers.serialize_session(row) if row else None


async def _detail_map(db, session_id: int) -> dict[int, object]:
    """Map stream_event_id -> extension detail ORM, across all extension tables."""
    detail: dict[int, object] = {}
    for model in (ProblemAttempt, CFProblemAttempt, ProjectLog, ClipLog):
        rows = (
            await db.execute(
                select(model)
                .join(StreamEvent, model.stream_event_id == StreamEvent.id)
                .where(StreamEvent.session_id == session_id)
            )
        ).scalars().all()
        for r in rows:
            detail[r.stream_event_id] = r
    return detail


async def get_markers(session_id: int) -> list[dict] | None:
    async with get_session() as db:
        session = await db.get(StreamSession, session_id)
        if session is None:
            return None
        events = (
            await db.execute(
                select(StreamEvent)
                .where(StreamEvent.session_id == session_id)
                .order_by(StreamEvent.timestamp)
            )
        ).scalars().all()
        detail = await _detail_map(db, session_id)
        start = session.start_time
    return [
        serializers.serialize_marker(e, start, detail.get(e.id)) for e in events
    ]


async def get_recap(session_id: int) -> dict | None:
    async with get_session() as db:
        session = await db.get(StreamSession, session_id)
        if session is None:
            return None
        problems = (
            await db.execute(
                select(ProblemAttempt)
                .join(StreamEvent, ProblemAttempt.stream_event_id == StreamEvent.id)
                .where(StreamEvent.session_id == session_id)
                .order_by(StreamEvent.timestamp)
            )
        ).scalars().all()
        projects = (
            await db.execute(
                select(ProjectLog)
                .join(StreamEvent, ProjectLog.stream_event_id == StreamEvent.id)
                .where(StreamEvent.session_id == session_id)
                .order_by(StreamEvent.timestamp)
            )
        ).scalars().all()
        clip_count = (
            await db.execute(
                select(func.count(ClipLog.id))
                .join(StreamEvent, ClipLog.stream_event_id == StreamEvent.id)
                .where(StreamEvent.session_id == session_id)
            )
        ).scalar_one()
        recap = serializers.serialize_recap(
            session,
            [
                {
                    "title": p.title,
                    "difficulty": p.difficulty,
                    "rating": p.rating,
                    "vod_timestamp": p.vod_timestamp,
                }
                for p in problems
            ],
            [
                {"title": p.title, "url": p.url, "vod_timestamp": p.vod_timestamp}
                for p in projects
            ],
            int(clip_count or 0),
        )
    return recap
