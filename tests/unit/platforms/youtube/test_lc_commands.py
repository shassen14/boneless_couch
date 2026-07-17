# tests/unit/platforms/youtube/test_lc_commands.py
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select

from couchd.core.models import ProblemAttempt, ProblemPost, SolutionPost
from couchd.platforms.youtube.components.lc_commands import LCCommands

_MOD = "couchd.platforms.youtube.components.lc_commands"


@pytest.fixture
def cog():
    return LCCommands(lc_client=MagicMock(), mod_engine=MagicMock(), chat_client=MagicMock())


def _ctx(content, *, broadcaster=False, moderator=False, uid="1"):
    ctx = MagicMock()
    ctx.content = content
    ctx.author.id = uid
    ctx.author.broadcaster = broadcaster
    ctx.author.moderator = moderator
    ctx.reply = AsyncMock()
    return ctx


# ── cmd_lc show ───────────────────────────────────────────────────────────────

async def test_show_no_session(cog):
    ctx = _ctx("!lc")
    with patch(f"{_MOD}.get_active_session", AsyncMock(return_value=None)):
        await cog.cmd_lc(ctx)
    ctx.reply.assert_awaited_once_with("No active stream session.")


async def test_show_none_logged(cog, get_session_fn, stream_session):
    ctx = _ctx("!lc")
    with patch(f"{_MOD}.get_active_session", AsyncMock(return_value=stream_session)), \
         patch(f"{_MOD}.get_session", get_session_fn):
        await cog.cmd_lc(ctx)
    ctx.reply.assert_awaited_once_with("No LeetCode problem logged yet.")


async def test_show_returns_url(cog, get_session_fn, lc_event, stream_session):
    ctx = _ctx("!lc")
    with patch(f"{_MOD}.get_active_session", AsyncMock(return_value=stream_session)), \
         patch(f"{_MOD}.get_session", get_session_fn):
        await cog.cmd_lc(ctx)
    ctx.reply.assert_awaited_once_with(lc_event.url)


# ── cmd_lc log ────────────────────────────────────────────────────────────────

async def test_log_non_privileged_ignored(cog):
    ctx = _ctx("!lc https://leetcode.com/problems/two-sum/")
    with patch(f"{_MOD}.get_active_session", AsyncMock()) as gas:
        await cog.cmd_lc(ctx)
    gas.assert_not_awaited()


async def test_log_invalid_url(cog):
    ctx = _ctx("!lc https://example.com/x", broadcaster=True)
    await cog.cmd_lc(ctx)
    ctx.reply.assert_awaited_once_with("Invalid LeetCode URL.")


async def test_log_no_session(cog):
    ctx = _ctx("!lc https://leetcode.com/problems/two-sum/", moderator=True)
    with patch(f"{_MOD}.get_active_session", AsyncMock(return_value=None)):
        await cog.cmd_lc(ctx)
    ctx.reply.assert_awaited_once_with("No active stream session found in DB.")


async def test_log_fetch_failure(cog, stream_session):
    cog.lc_client.fetch_problem = AsyncMock(return_value=None)
    ctx = _ctx("!lc https://leetcode.com/problems/two-sum/", broadcaster=True)
    with patch(f"{_MOD}.get_active_session", AsyncMock(return_value=stream_session)):
        await cog.cmd_lc(ctx)
    ctx.reply.assert_awaited_once_with("Could not fetch problem data from LeetCode.")


async def test_log_success_with_rating(cog, get_session_fn, db_session, stream_session):
    cog.lc_client.fetch_problem = AsyncMock(return_value={
        "id": 1, "title": "Two Sum", "difficulty": "Easy", "tags": [],
    })
    cog.lc_client.get_rating = MagicMock(return_value=1234.6)
    ctx = _ctx("!lc https://leetcode.com/problems/two-sum/", broadcaster=True)
    with patch(f"{_MOD}.get_active_session", AsyncMock(return_value=stream_session)), \
         patch(f"{_MOD}.get_session", get_session_fn):
        await cog.cmd_lc(ctx)
    rows = (await db_session.execute(select(ProblemAttempt))).scalars().all()
    assert len(rows) == 1
    assert rows[0].slug == "two-sum"
    assert rows[0].rating == 1235
    assert "Rating: 1235" in ctx.reply.call_args.args[0]


async def test_log_success_without_rating(cog, get_session_fn, db_session, stream_session):
    cog.lc_client.fetch_problem = AsyncMock(return_value={
        "id": 5, "title": "X", "difficulty": "Hard", "tags": [],
    })
    cog.lc_client.get_rating = MagicMock(return_value=None)
    ctx = _ctx("!lc https://leetcode.com/problems/x/", broadcaster=True)
    with patch(f"{_MOD}.get_active_session", AsyncMock(return_value=stream_session)), \
         patch(f"{_MOD}.get_session", get_session_fn):
        await cog.cmd_lc(ctx)
    assert "Rating" not in ctx.reply.call_args.args[0]


# ── _check_solution_url ───────────────────────────────────────────────────────

def _raw(name="alice"):
    return {"authorDetails": {"displayName": name}}


async def test_solution_no_match_ignored(cog):
    gs = MagicMock()
    with patch(f"{_MOD}.get_session", gs):
        await cog._check_solution_url(_raw(), "just chatting")
    gs.assert_not_called()


async def test_solution_slug_form_upserts(cog, get_session_fn, db_session, stream_session):
    db_session.add(ProblemPost(platform_id="two-sum", forum_thread_id=999))
    await db_session.commit()
    text = "https://leetcode.com/problems/two-sum/submissions/123456/"
    with patch(f"{_MOD}.get_active_session", AsyncMock(return_value=stream_session)), \
         patch(f"{_MOD}.get_session", get_session_fn):
        await cog._check_solution_url(_raw("alice"), text)
    rows = (await db_session.execute(select(SolutionPost))).scalars().all()
    assert len(rows) == 1
    assert rows[0].problem_slug == "two-sum"
    assert rows[0].username == "alice"
    assert rows[0].platform == "youtube"


async def test_solution_slug_form_no_problem_post_skips(cog, get_session_fn, db_session, stream_session):
    text = "https://leetcode.com/problems/unknown/submissions/123/"
    with patch(f"{_MOD}.get_active_session", AsyncMock(return_value=stream_session)), \
         patch(f"{_MOD}.get_session", get_session_fn):
        await cog._check_solution_url(_raw(), text)
    rows = (await db_session.execute(select(SolutionPost))).scalars().all()
    assert rows == []


async def test_solution_bare_form_uses_current_attempt(cog, get_session_fn, db_session, lc_event, stream_session):
    text = "https://leetcode.com/submissions/detail/987654/"
    with patch(f"{_MOD}.get_active_session", AsyncMock(return_value=stream_session)), \
         patch(f"{_MOD}.get_session", get_session_fn):
        await cog._check_solution_url(_raw("bob"), text)
    rows = (await db_session.execute(select(SolutionPost))).scalars().all()
    assert len(rows) == 1
    assert rows[0].problem_slug == lc_event.slug
    assert rows[0].username == "bob"


async def test_solution_bare_form_no_session_skips(cog, get_session_fn, db_session):
    text = "https://leetcode.com/submissions/detail/987654/"
    with patch(f"{_MOD}.get_active_session", AsyncMock(return_value=None)), \
         patch(f"{_MOD}.get_session", get_session_fn):
        await cog._check_solution_url(_raw(), text)
    rows = (await db_session.execute(select(SolutionPost))).scalars().all()
    assert rows == []
