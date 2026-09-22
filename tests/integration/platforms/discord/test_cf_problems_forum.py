# tests/integration/platforms/discord/test_cf_problems_forum.py
#
# CF forum + solution flow against a real SQLite in-memory database. Discord is mocked.
from contextlib import ExitStack
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select

from couchd.core.constants import Platform
from couchd.core.models import (
    CFProblemAttempt,
    CFProblemPost,
    SolutionPost,
    StreamEvent,
)
from couchd.core.solutions import record_cf_solution
from couchd.platforms.discord.components.cf_problems_forum import (
    build_cf_embed,
    sync_cf_problem,
)
from couchd.platforms.discord.components.problems_forum import flush_pending_solutions

_SUBMISSION = "https://codeforces.com/contest/1883/submission/391276739"
_GET_SESSION_PATCHES = [
    "couchd.core.solutions.get_session",
    "couchd.core.utils.get_session",
    "couchd.platforms.discord.components.cf_problems_forum.get_session",
    "couchd.platforms.discord.components.problems_forum.get_session",
]


@pytest.fixture
def patched_db(get_session_fn):
    with ExitStack() as stack:
        for target in _GET_SESSION_PATCHES:
            stack.enter_context(patch(target, get_session_fn))
        yield


@pytest.fixture
async def cf_attempt(db_session, stream_session):
    event = StreamEvent(session_id=stream_session.id, event_type="cf_problem")
    db_session.add(event)
    await db_session.flush()
    attempt = CFProblemAttempt(
        stream_event_id=event.id,
        contest_id=1883,
        index="C",
        title="Raspberries",
        url="https://codeforces.com/contest/1883/problem/C",
        rating=1400,
        vod_timestamp="01h22m12s",
    )
    db_session.add(attempt)
    await db_session.commit()
    return attempt


async def _solutions(db_session):
    return (await db_session.execute(select(SolutionPost))).scalars().all()


async def test_build_embed_finds_attempt_by_problem_id(patched_db, cf_attempt):
    # Regression: problem_id was a plain @property, so this query matched nothing.
    name, embed, attempts = await build_cf_embed("1883C")
    assert name == "1883C · Raspberries"
    assert embed.title == "Raspberries"
    assert len(attempts) == 1


async def test_sync_creates_thread_and_posts_solution(patched_db, cf_attempt, db_session):
    db_session.add(SolutionPost(
        problem_slug="1883C", platform="twitch", username="v", url=_SUBMISSION
    ))
    await db_session.commit()

    thread = MagicMock(id=555)
    thread.send = AsyncMock(return_value=MagicMock(id=777))
    forum = MagicMock()
    forum.create_thread = AsyncMock(return_value=thread)

    await sync_cf_problem(forum, "1883C", MagicMock())

    forum.create_thread.assert_awaited_once()
    post = (await db_session.execute(select(CFProblemPost))).scalar_one()
    assert (post.problem_id, post.forum_thread_id) == ("1883C", 555)
    thread.send.assert_awaited_once()
    sol = (await _solutions(db_session))[0]
    await db_session.refresh(sol)
    assert sol.discord_message_id == 777


async def test_flush_pending_uses_cf_thread_table(patched_db, db_session):
    db_session.add(CFProblemPost(problem_id="1883C", forum_thread_id=222))
    db_session.add(SolutionPost(
        problem_slug="1883C", platform="twitch", username="v", url=_SUBMISSION
    ))
    await db_session.commit()

    thread = MagicMock()
    thread.send = AsyncMock(return_value=MagicMock(id=1))
    forum = MagicMock()
    forum.get_thread = MagicMock(return_value=thread)

    await flush_pending_solutions(forum, MagicMock(), CFProblemPost.problem_id)

    forum.get_thread.assert_called_once_with(222)
    thread.send.assert_awaited_once()


async def test_record_cf_solution_for_current_problem(patched_db, cf_attempt, db_session):
    await record_cf_solution(f"done {_SUBMISSION}", Platform.TWITCH, "viewer1")

    sols = await _solutions(db_session)
    assert [(s.problem_slug, s.platform, s.username, s.url) for s in sols] == [
        ("1883C", "twitch", "viewer1", _SUBMISSION)
    ]


async def test_record_cf_solution_ignores_other_contest(patched_db, cf_attempt, db_session):
    await record_cf_solution(
        "https://codeforces.com/contest/1/submission/5", Platform.TWITCH, "viewer1"
    )
    assert await _solutions(db_session) == []


async def test_record_cf_solution_needs_active_session(patched_db, db_session):
    await record_cf_solution(_SUBMISSION, Platform.TWITCH, "viewer1")
    assert await _solutions(db_session) == []
