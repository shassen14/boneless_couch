# tests/unit/platforms/twitch/test_lc_command.py
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select

from couchd.core.models import ProblemPost, SolutionPost, ProblemAttempt
from couchd.platforms.twitch.components.lc_commands import LCCommands

_MOD = "couchd.platforms.twitch.components.lc_commands"


@pytest.fixture
def cog():
    return LCCommands(lc_client=MagicMock(), metrics_tracker=MagicMock(), mod_engine=MagicMock())


async def _run(cog, ctx):
    """Invoke the !lc command's raw callback, bypassing the twitchio Command wrapper."""
    await type(cog).leetcode_command._callback(cog, ctx)


def _ctx(content, *, broadcaster=False, moderator=False, uid="1"):
    ctx = MagicMock()
    ctx.content = content
    ctx.author.id = uid
    ctx.author.broadcaster = broadcaster
    ctx.author.moderator = moderator
    ctx.reply = AsyncMock()
    return ctx


def _patches(session=None, get_session_fn=None):
    return (
        patch(f"{_MOD}.get_active_session", AsyncMock(return_value=session)),
        patch(f"{_MOD}.get_session", get_session_fn or MagicMock()),
    )


# ── !lc (show current) ────────────────────────────────────────────────────────

async def test_show_no_active_session_warns(cog):
    ctx = _ctx("!lc")
    p1, p2 = _patches(session=None)
    with p1, p2:
        await _run(cog, ctx)
    ctx.reply.assert_awaited_once_with("⚠️ No active stream session.")


async def test_show_returns_current_problem_url(cog, get_session_fn, lc_event, stream_session):
    ctx = _ctx("!lc")
    with patch(f"{_MOD}.get_active_session", AsyncMock(return_value=stream_session)), \
         patch(f"{_MOD}.get_session", get_session_fn):
        await _run(cog, ctx)
    ctx.reply.assert_awaited_once_with(lc_event.url)


async def test_show_no_problem_logged(cog, get_session_fn, stream_session):
    ctx = _ctx("!lc")
    with patch(f"{_MOD}.get_active_session", AsyncMock(return_value=stream_session)), \
         patch(f"{_MOD}.get_session", get_session_fn):
        await _run(cog, ctx)
    ctx.reply.assert_awaited_once_with("No LeetCode problem logged yet.")


async def test_show_respects_cooldown(cog):
    ctx = _ctx("!lc")
    # Second invocation within the window is silently dropped.
    with patch(f"{_MOD}.get_active_session", AsyncMock(return_value=None)):
        await _run(cog, ctx)
        ctx.reply.reset_mock()
        await _run(cog, ctx)
    ctx.reply.assert_not_awaited()


# ── !lc <url> (log new) — authorization & validation ──────────────────────────

async def test_log_rejected_for_non_privileged_user(cog):
    ctx = _ctx("!lc https://leetcode.com/problems/two-sum/", broadcaster=False, moderator=False)
    with patch(f"{_MOD}.get_active_session", AsyncMock()) as gas:
        await _run(cog, ctx)
    ctx.reply.assert_not_awaited()
    gas.assert_not_called()  # bails before touching the DB


async def test_log_invalid_url(cog):
    ctx = _ctx("!lc https://example.com/foo", broadcaster=True)
    await _run(cog, ctx)
    ctx.reply.assert_awaited_once_with("Invalid LeetCode URL.")


async def test_log_no_active_session(cog):
    ctx = _ctx("!lc https://leetcode.com/problems/two-sum/", moderator=True)
    with patch(f"{_MOD}.get_active_session", AsyncMock(return_value=None)):
        await _run(cog, ctx)
    assert "No active stream session" in ctx.reply.await_args[0][0]


async def test_log_fetch_failure(cog, stream_session):
    ctx = _ctx("!lc https://leetcode.com/problems/two-sum/", broadcaster=True)
    cog.lc_client.fetch_problem = AsyncMock(return_value=None)
    with patch(f"{_MOD}.get_active_session", AsyncMock(return_value=stream_session)):
        await _run(cog, ctx)
    ctx.reply.assert_awaited_once_with("❌ Could not fetch problem data from LeetCode.")


async def test_log_success_persists_attempt(cog, get_session_fn, db_session, stream_session):
    ctx = _ctx("!lc https://leetcode.com/problems/two-sum/", broadcaster=True)
    cog.lc_client.fetch_problem = AsyncMock(
        return_value={"id": 1, "title": "Two Sum", "difficulty": "Easy"}
    )
    cog.lc_client.get_rating = MagicMock(return_value=1234.7)

    with patch(f"{_MOD}.get_active_session", AsyncMock(return_value=stream_session)), \
         patch(f"{_MOD}.get_session", get_session_fn), \
         patch(f"{_MOD}.compute_vod_timestamp", return_value="00h10m00s"):
        await _run(cog, ctx)

    rows = (await db_session.execute(select(ProblemAttempt))).scalars().all()
    assert len(rows) == 1
    assert rows[0].slug == "two-sum"
    assert rows[0].rating == 1235  # rounded
    reply = ctx.reply.await_args[0][0]
    assert "1. Two Sum" in reply and "1235" in reply and "00h10m00s" in reply


# ── event_message listener (chat routing) ─────────────────────────────────────

def _payload(text, *, chatter_id="9", name="viewer", badges=()):
    p = MagicMock()
    p.chatter.id = chatter_id
    p.chatter.name = name
    p.chatter.display_name = name.title()
    p.text = text
    p.colour = None
    p.badges = [MagicMock(set_id=b) for b in badges]
    p.id = "msg-1"
    p.fragments = []
    return p


async def _emit(cog, payload):
    await cog.event_message(payload)


async def test_event_message_bot_echo_skips_metrics_and_mod(cog):
    cog.metrics_tracker.record_message = MagicMock()
    # Bot id matches conftest's TWITCH_BOT_ID ("12345").
    payload = _payload("hello", chatter_id="12345")
    with patch(f"{_MOD}.veil.post_event", AsyncMock()) as post:
        await _emit(cog, payload)
    post.assert_awaited_once()
    assert post.await_args[0][0] == "twitch.chat.message"
    cog.metrics_tracker.record_message.assert_not_called()
    cog.mod_engine.is_flagged.assert_not_called()


async def test_event_message_normal_records_and_posts(cog):
    cog.metrics_tracker.record_message = MagicMock()
    cog.mod_engine.is_flagged = MagicMock(return_value=False)
    payload = _payload("just chatting")
    with patch(f"{_MOD}.veil.post_event", AsyncMock()) as post, \
         patch.object(cog, "_check_solution_url", AsyncMock()) as check:
        await _emit(cog, payload)
    cog.metrics_tracker.record_message.assert_called_once()
    check.assert_awaited_once_with(payload)
    assert post.await_args[0][0] == "twitch.chat.message"


async def test_event_message_flagged_holds_and_stops(cog):
    cog.metrics_tracker.record_message = MagicMock()
    cog.mod_engine.is_flagged = MagicMock(return_value=True)
    cog.mod_engine.add_pending = MagicMock()
    payload = _payload("nasty words")
    with patch(f"{_MOD}.veil.post_event", AsyncMock()) as post, \
         patch.object(cog, "_check_solution_url", AsyncMock()):
        await _emit(cog, payload)
    cog.mod_engine.add_pending.assert_called_once()
    # Only the modqueue.pending event is posted — not the public chat message.
    assert post.await_count == 1
    assert post.await_args[0][0] == "modqueue.pending"


# ── _check_solution_url (passive submission detection) ────────────────────────

_SLUG_URL = "https://leetcode.com/problems/two-sum/submissions/123456/"
_BARE_URL = "https://leetcode.com/submissions/detail/987654/"


async def _check(cog, text, session, get_session_fn, name="solver"):
    payload = _payload(text, name=name)
    with patch(f"{_MOD}.get_active_session", AsyncMock(return_value=session)), \
         patch(f"{_MOD}.get_session", get_session_fn), \
         patch(f"{_MOD}.compute_vod_timestamp", return_value="00h05m00s"):
        await cog._check_solution_url(payload)


async def _solutions(db):
    return (await db.execute(select(SolutionPost))).scalars().all()


async def test_check_solution_no_submission_url_is_noop(cog, get_session_fn, db_session, stream_session):
    await _check(cog, "just a normal message", stream_session, get_session_fn)
    assert await _solutions(db_session) == []


async def test_check_solution_slug_without_problem_post_is_skipped(cog, get_session_fn, db_session, stream_session):
    await _check(cog, _SLUG_URL, stream_session, get_session_fn)
    assert await _solutions(db_session) == []


async def test_check_solution_slug_with_problem_post_creates_solution(cog, get_session_fn, db_session, stream_session):
    db_session.add(ProblemPost(platform_id="two-sum", forum_thread_id=1))
    await db_session.commit()

    await _check(cog, _SLUG_URL, stream_session, get_session_fn, name="alice")

    rows = await _solutions(db_session)
    assert len(rows) == 1
    assert rows[0].problem_slug == "two-sum"
    assert rows[0].username == "alice"
    assert rows[0].url == _SLUG_URL
    assert rows[0].vod_timestamp == "00h05m00s"


async def test_check_solution_bare_url_uses_latest_attempt_slug(cog, get_session_fn, db_session, stream_session, lc_event):
    # lc_event seeds a ProblemAttempt (slug "two-sum") on the active session.
    await _check(cog, _BARE_URL, stream_session, get_session_fn, name="bob")

    rows = await _solutions(db_session)
    assert len(rows) == 1
    assert rows[0].problem_slug == "two-sum"
    assert rows[0].url == _BARE_URL


async def test_check_solution_bare_url_without_session_is_skipped(cog, get_session_fn, db_session):
    await _check(cog, _BARE_URL, None, get_session_fn)
    assert await _solutions(db_session) == []


async def test_check_solution_resubmission_updates_existing(cog, get_session_fn, db_session, stream_session):
    db_session.add(ProblemPost(platform_id="two-sum", forum_thread_id=1))
    db_session.add(
        SolutionPost(problem_slug="two-sum", platform="twitch", username="alice", url="old-url")
    )
    await db_session.commit()

    await _check(cog, _SLUG_URL, stream_session, get_session_fn, name="alice")

    rows = await _solutions(db_session)
    assert len(rows) == 1  # updated in place, not duplicated
    assert rows[0].url == _SLUG_URL
