# tests/unit/platforms/twitch/test_cf_command.py
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select

from couchd.core.clients import codeforces
from couchd.core.models import CFProblemAttempt, StreamEvent
from couchd.platforms.twitch.components.cf_commands import CFCommands

_MOD = "couchd.platforms.twitch.components.cf_commands"


@pytest.fixture
def cog():
    return CFCommands()


async def _run(cog, ctx):
    await type(cog).cf_command._callback(cog, ctx)


def _ctx(content, *, broadcaster=False, moderator=False, uid="1"):
    ctx = MagicMock()
    ctx.content = content
    ctx.author.id = uid
    ctx.author.broadcaster = broadcaster
    ctx.author.moderator = moderator
    ctx.reply = AsyncMock()
    return ctx


# ── !cf (show) ────────────────────────────────────────────────────────────────

async def test_show_no_active_session(cog):
    ctx = _ctx("!cf")
    with patch(f"{_MOD}.get_active_session", AsyncMock(return_value=None)):
        await _run(cog, ctx)
    ctx.reply.assert_awaited_once_with("⚠️ No active stream session.")


async def test_show_none_logged(cog, get_session_fn, stream_session):
    ctx = _ctx("!cf")
    with patch(f"{_MOD}.get_active_session", AsyncMock(return_value=stream_session)), \
         patch(f"{_MOD}.get_session", get_session_fn):
        await _run(cog, ctx)
    ctx.reply.assert_awaited_once_with("No Codeforces problem logged yet this stream.")


async def test_show_current(cog, get_session_fn, db_session, stream_session):
    event = StreamEvent(session_id=stream_session.id, event_type="cf_problem")
    db_session.add(event)
    await db_session.flush()
    db_session.add(CFProblemAttempt(
        stream_event_id=event.id, contest_id=1700, index="A",
        title="Factorial", url="https://codeforces.com/problemset/problem/1700/A",
    ))
    await db_session.commit()

    ctx = _ctx("!cf")
    with patch(f"{_MOD}.get_active_session", AsyncMock(return_value=stream_session)), \
         patch(f"{_MOD}.get_session", get_session_fn):
        await _run(cog, ctx)
    ctx.reply.assert_awaited_once_with(
        "📌 1700A · Factorial → https://codeforces.com/problemset/problem/1700/A"
    )


# ── !cf <url> (log) ───────────────────────────────────────────────────────────

def _patch_cf_client(resolved):
    """Patch the client module but keep the real describe() formatting."""
    patcher = patch(f"{_MOD}.cf_client")
    cf = patcher.start()
    cf.resolve_problem = AsyncMock(return_value=resolved)
    cf.describe = codeforces.describe
    return patcher, cf


async def test_log_non_privileged_ignored(cog):
    ctx = _ctx("!cf https://codeforces.com/problemset/problem/1700/A")
    patcher, cf = _patch_cf_client(None)
    try:
        await _run(cog, ctx)
    finally:
        patcher.stop()
    cf.resolve_problem.assert_not_called()
    ctx.reply.assert_not_awaited()


async def test_log_invalid_url(cog):
    ctx = _ctx("!cf bogus", broadcaster=True)
    patcher, _ = _patch_cf_client(None)
    try:
        await _run(cog, ctx)
    finally:
        patcher.stop()
    ctx.reply.assert_awaited_once_with("❌ Invalid Codeforces problem URL.")


async def test_log_persists_and_replies(cog, get_session_fn, db_session, stream_session):
    ctx = _ctx("!cf https://codeforces.com/problemset/problem/1700/A", broadcaster=True)
    patcher, _ = _patch_cf_client({
        "contest_id": 1700, "index": "A",
        "url": "https://codeforces.com/contest/1700/problem/A",
        "title": "Factorial", "rating": 800, "tags": ["math", "greedy"],
    })
    try:
        with patch(f"{_MOD}.get_active_session", AsyncMock(return_value=stream_session)), \
             patch(f"{_MOD}.get_session", get_session_fn):
            await _run(cog, ctx)
    finally:
        patcher.stop()

    rows = (await db_session.execute(select(CFProblemAttempt))).scalars().all()
    assert len(rows) == 1
    assert rows[0].title == "Factorial"
    assert rows[0].contest_id == 1700
    assert rows[0].tags == "math, greedy"
    assert ctx.reply.call_args.args[0] == (
        "✅ CF: 1700A · Factorial · 800 → https://codeforces.com/contest/1700/problem/A"
    )


async def test_log_unrated_problem_passes_typed_title(cog, get_session_fn, db_session, stream_session):
    """Gym/edu problems have no API metadata; the trailing text becomes the title."""
    url = "https://codeforces.com/edu/course/2/lesson/7/1/practice/contest/289390/problem/C"
    ctx = _ctx(f"!cf {url} Number of Inversions", broadcaster=True)
    patcher, cf = _patch_cf_client({
        "contest_id": 289390, "index": "C", "url": url,
        "title": "Number of Inversions", "rating": None, "tags": [],
    })
    try:
        with patch(f"{_MOD}.get_active_session", AsyncMock(return_value=stream_session)), \
             patch(f"{_MOD}.get_session", get_session_fn):
            await _run(cog, ctx)
    finally:
        patcher.stop()

    cf.resolve_problem.assert_awaited_once_with(url, "Number of Inversions")
    rows = (await db_session.execute(select(CFProblemAttempt))).scalars().all()
    assert len(rows) == 1
    assert rows[0].title == "Number of Inversions"
    assert rows[0].url == url
    assert rows[0].rating is None
    assert ctx.reply.call_args.args[0] == f"✅ CF: 289390C · Number of Inversions → {url}"
