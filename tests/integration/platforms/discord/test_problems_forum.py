# tests/integration/platforms/discord/test_problems_forum.py
#
# Tests the problems forum functions against a real SQLite in-memory database.
# External services (LeetCode API, Discord) are mocked; only the DB layer is real.
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from discord.ext import tasks
from sqlalchemy import select

import discord

from couchd.core.models import ProblemPost, SolutionPost
from couchd.platforms.discord.cogs.problems import ProblemsWatcherCog
from couchd.platforms.discord.components.problems_forum import (
    build_problem_embed,
    create_problem_thread,
    flush_pending_solutions,
    resolve_tags,
    sync_solution_comments,
)

_FORUM_PATCH = "couchd.platforms.discord.components.problems_forum.get_session"
_COG_PATCH = "couchd.platforms.discord.cogs.problems.get_session"


@pytest.fixture
def cog():
    with patch.object(tasks.Loop, "start"):
        return ProblemsWatcherCog(MagicMock())


# ── build_problem_embed ───────────────────────────────────────────────────────


async def test_build_embed_lc_only_shows_attempted(get_session_fn, lc_event):
    with patch(_FORUM_PATCH, get_session_fn):
        name, embed, events = await build_problem_embed("two-sum")

    assert name == "1. Two Sum"
    assert embed is not None
    assert embed.title == "1. Two Sum"
    field_names = [f.name for f in embed.fields]
    assert any("Difficulty" in n for n in field_names)
    assert any("Appearances" in n for n in field_names)
    assert any("Status" in n for n in field_names)
    status_field = next(f for f in embed.fields if "Status" in f.name)
    assert "Attempted" in status_field.value
    assert len(events) == 1


async def test_build_embed_with_solution_hides_status(
    get_session_fn, lc_event, db_session
):
    solution = SolutionPost(
        problem_slug="two-sum",
        platform="twitch",
        username="teststreamer",
        url="https://leetcode.com/submissions/detail/100/",
        vod_timestamp="00h45m00s",
    )
    db_session.add(solution)
    await db_session.commit()

    with patch(_FORUM_PATCH, get_session_fn):
        _, embed, _ = await build_problem_embed("two-sum")

    field_names = [f.name for f in embed.fields]
    assert not any("Status" in n for n in field_names)


# ── _poll_streamer_solutions ──────────────────────────────────────────────────


async def test_poll_inserts_solution(
    cog, get_session_fn, db_engine, stream_session, lc_event
):
    cog.lc_client.fetch_recent_ac_submissions = AsyncMock(
        return_value=[{"id": "999", "titleSlug": "two-sum", "timestamp": "1700000000"}]
    )

    with (
        patch(
            "couchd.platforms.discord.cogs.problems.get_active_session",
            AsyncMock(return_value=stream_session),
        ),
        patch(_COG_PATCH, get_session_fn),
        patch(
            "couchd.platforms.discord.cogs.problems.compute_vod_timestamp",
            return_value="00h55m00s",
        ),
    ):
        await cog._poll_streamer_solutions()

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    factory = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)
    async with factory() as verify_session:
        solutions = (await verify_session.execute(select(SolutionPost))).scalars().all()

    assert len(solutions) == 1
    assert solutions[0].problem_slug == "two-sum"
    assert solutions[0].username == "teststreamer"
    assert "999" in solutions[0].url
    assert solutions[0].vod_timestamp == "00h55m00s"


async def test_poll_does_not_insert_duplicate(
    cog, get_session_fn, db_engine, stream_session, lc_event, db_session
):
    existing = SolutionPost(
        problem_slug="two-sum",
        platform="twitch",
        username="teststreamer",
        url="https://leetcode.com/submissions/detail/999/",
        vod_timestamp="00h50m00s",
    )
    db_session.add(existing)
    await db_session.commit()

    cog.lc_client.fetch_recent_ac_submissions = AsyncMock(
        return_value=[{"id": "999", "titleSlug": "two-sum", "timestamp": "1700000000"}]
    )

    with (
        patch(
            "couchd.platforms.discord.cogs.problems.get_active_session",
            AsyncMock(return_value=stream_session),
        ),
        patch(_COG_PATCH, get_session_fn),
        patch(
            "couchd.platforms.discord.cogs.problems.compute_vod_timestamp",
            return_value="01h00m00s",
        ),
    ):
        await cog._poll_streamer_solutions()

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    factory = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)
    async with factory() as verify_session:
        solutions = (await verify_session.execute(select(SolutionPost))).scalars().all()

    assert len(solutions) == 1  # still just the original, no duplicate


# ── resolve_tags ──────────────────────────────────────────────────────────────


def _tag(name):
    t = MagicMock()
    t.name = name
    return t


def test_resolve_tags_matches_difficulty():
    forum = MagicMock()
    forum.available_tags = [_tag("Easy"), _tag("Medium"), _tag("Hard")]
    result = resolve_tags(forum, "Medium")
    assert [t.name for t in result] == ["Medium"]


def test_resolve_tags_none_difficulty_returns_empty():
    forum = MagicMock()
    forum.available_tags = [_tag("Easy")]
    assert resolve_tags(forum, None) == []


def test_resolve_tags_unknown_difficulty_returns_empty():
    forum = MagicMock()
    forum.available_tags = [_tag("Easy"), _tag("Hard")]
    assert resolve_tags(forum, "Insane") == []


# ── sync_solution_comments ────────────────────────────────────────────────────


async def test_sync_solution_posts_new_message_and_records_id(
    get_session_fn, db_session
):
    sol = SolutionPost(
        problem_slug="two-sum",
        platform="twitch",
        username="viewerA",
        url="https://leetcode.com/submissions/detail/1/",
        vod_timestamp="00h10m00s",
    )
    db_session.add(sol)
    await db_session.commit()

    thread = MagicMock()
    thread.send = AsyncMock(return_value=MagicMock(id=42424242))

    with patch(_FORUM_PATCH, get_session_fn):
        await sync_solution_comments(thread, "two-sum")

    thread.send.assert_awaited_once()
    assert "viewerA" in thread.send.call_args.args[0]

    refreshed = (
        await db_session.execute(select(SolutionPost))
    ).scalars().all()
    assert refreshed[0].discord_message_id == 42424242


async def test_sync_solution_edits_existing_message(get_session_fn, db_session):
    sol = SolutionPost(
        problem_slug="two-sum",
        platform="twitch",
        username="viewerB",
        url="https://leetcode.com/submissions/detail/2/",
        vod_timestamp="00h20m00s",
        discord_message_id=555,
    )
    db_session.add(sol)
    await db_session.commit()

    existing_msg = MagicMock()
    existing_msg.edit = AsyncMock()
    thread = MagicMock()
    thread.fetch_message = AsyncMock(return_value=existing_msg)
    thread.send = AsyncMock()

    with patch(_FORUM_PATCH, get_session_fn):
        await sync_solution_comments(thread, "two-sum")

    thread.fetch_message.assert_awaited_once_with(555)
    existing_msg.edit.assert_awaited_once()
    thread.send.assert_not_called()  # edited, not re-posted


async def test_sync_solution_reposts_when_message_deleted(get_session_fn, db_session):
    sol = SolutionPost(
        problem_slug="two-sum",
        platform="twitch",
        username="viewerC",
        url="https://leetcode.com/submissions/detail/3/",
        vod_timestamp="00h30m00s",
        discord_message_id=999,
    )
    db_session.add(sol)
    await db_session.commit()

    thread = MagicMock()
    thread.fetch_message = AsyncMock(
        side_effect=discord.NotFound(MagicMock(status=404), "gone")
    )
    thread.send = AsyncMock(return_value=MagicMock(id=777))

    with patch(_FORUM_PATCH, get_session_fn):
        await sync_solution_comments(thread, "two-sum")

    thread.send.assert_awaited_once()  # fell through to a fresh post
    db_session.expire_all()  # drop cached attrs so the select reloads from DB
    refreshed = (await db_session.execute(select(SolutionPost))).scalars().all()
    assert refreshed[0].discord_message_id == 777


# ── create_problem_thread ─────────────────────────────────────────────────────


async def test_create_problem_thread_persists_problem_post(
    get_session_fn, lc_event, db_engine
):
    created_thread = MagicMock(id=313131)
    forum = MagicMock()
    forum.available_tags = [_tag("Easy")]
    forum.create_thread = AsyncMock(return_value=created_thread)

    with patch(_FORUM_PATCH, get_session_fn):
        thread, post = await create_problem_thread(forum, "two-sum")

    assert thread is created_thread
    assert post is not None
    forum.create_thread.assert_awaited_once()
    # Easy tag applied from the attempt difficulty.
    assert [t.name for t in forum.create_thread.call_args.kwargs["applied_tags"]] == ["Easy"]

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    factory = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)
    async with factory() as verify:
        posts = (await verify.execute(select(ProblemPost))).scalars().all()
    assert len(posts) == 1
    assert posts[0].platform_id == "two-sum"
    assert posts[0].forum_thread_id == 313131


async def test_create_problem_thread_unknown_slug_returns_none(get_session_fn):
    forum = MagicMock()
    with patch(_FORUM_PATCH, get_session_fn):
        thread, post = await create_problem_thread(forum, "does-not-exist")
    assert thread is None and post is None
    forum.create_thread.assert_not_called()


async def test_create_problem_thread_swallows_discord_error(get_session_fn, lc_event):
    forum = MagicMock()
    forum.available_tags = []
    forum.create_thread = AsyncMock(side_effect=discord.HTTPException(MagicMock(), "boom"))

    with patch(_FORUM_PATCH, get_session_fn):
        thread, post = await create_problem_thread(forum, "two-sum")

    assert thread is None and post is None


# ── flush_pending_solutions ───────────────────────────────────────────────────


async def test_flush_pending_skips_slug_without_problem_post(
    get_session_fn, db_session
):
    # Solution exists but no ProblemPost/thread yet — must skip cleanly.
    sol = SolutionPost(
        problem_slug="orphan",
        platform="twitch",
        username="v",
        url="https://x/1",
        vod_timestamp="00h01m00s",
    )
    db_session.add(sol)
    await db_session.commit()

    forum = MagicMock()
    bot = MagicMock()
    with patch(_FORUM_PATCH, get_session_fn):
        await flush_pending_solutions(forum, bot)  # must not raise

    forum.get_thread.assert_not_called()


async def test_flush_pending_posts_via_cached_thread(get_session_fn, db_session):
    db_session.add(
        ProblemPost(platform_id="two-sum", forum_thread_id=222)
    )
    db_session.add(
        SolutionPost(
            problem_slug="two-sum",
            platform="twitch",
            username="v",
            url="https://x/1",
            vod_timestamp="00h01m00s",
        )
    )
    await db_session.commit()

    thread = MagicMock()
    thread.send = AsyncMock(return_value=MagicMock(id=4321))
    forum = MagicMock()
    forum.get_thread = MagicMock(return_value=thread)

    with patch(_FORUM_PATCH, get_session_fn):
        await flush_pending_solutions(forum, MagicMock())

    forum.get_thread.assert_called_once_with(222)
    thread.send.assert_awaited_once()
