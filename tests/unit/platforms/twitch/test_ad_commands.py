# tests/unit/platforms/twitch/test_ad_commands.py
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from couchd.platforms.twitch.components.ad_commands import AdCommands

_MOD = "couchd.platforms.twitch.components.ad_commands"


@pytest.fixture
def ad_manager():
    m = MagicMock()
    m.get_remaining = AsyncMock(return_value=180)
    m.log_ad = AsyncMock()
    m.cancel_pending = MagicMock()
    m.try_reserve_fire = MagicMock(return_value=True)
    m.release_fire = MagicMock()
    return m


@pytest.fixture
def cog(ad_manager):
    return AdCommands(bot=MagicMock(), ad_manager=ad_manager, youtube_client=None)


async def _run(cog, ctx):
    await type(cog).run_ad._callback(cog, ctx)


def _ctx(content, *, broadcaster=True, moderator=False):
    ctx = MagicMock()
    ctx.content = content
    ctx.author.broadcaster = broadcaster
    ctx.author.moderator = moderator
    ctx.reply = AsyncMock()
    ctx.channel.start_commercial = AsyncMock()
    return ctx


@pytest.fixture
def session():
    s = MagicMock()
    s.id = 1
    s.start_time = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    return s


@pytest.fixture(autouse=True)
def _quiet_side_effects():
    """Stub fire-and-forget pieces so tests don't leak tasks or touch chat."""
    def _drop_task(coro):
        coro.close()  # close the un-awaited coroutine to avoid RuntimeWarning
        return MagicMock()

    with patch(f"{_MOD}.send_chat_message", AsyncMock()), \
         patch(f"{_MOD}.pick_ad_message", return_value=None), \
         patch(f"{_MOD}.pick_return_message", return_value="back!"), \
         patch(f"{_MOD}.asyncio.create_task", side_effect=_drop_task):
        yield


async def test_non_privileged_ignored(cog, ad_manager):
    ctx = _ctx("!ad", broadcaster=False, moderator=False)
    await _run(cog, ctx)
    ad_manager.get_remaining.assert_not_awaited()
    ctx.reply.assert_not_awaited()


async def test_no_active_session(cog):
    ctx = _ctx("!ad")
    with patch(f"{_MOD}.get_active_session", AsyncMock(return_value=None)):
        await _run(cog, ctx)
    ctx.reply.assert_awaited_once_with("⚠️ No active stream session.")


async def test_invalid_minutes_arg(cog, session):
    ctx = _ctx("!ad abc")
    with patch(f"{_MOD}.get_active_session", AsyncMock(return_value=session)):
        await _run(cog, ctx)
    ctx.reply.assert_awaited_once_with("Usage: !ad [minutes] — e.g. !ad 1.5 for 90s")


async def test_quota_met_no_arg(cog, ad_manager, session):
    ad_manager.get_remaining = AsyncMock(return_value=0)
    ctx = _ctx("!ad")
    with patch(f"{_MOD}.get_active_session", AsyncMock(return_value=session)):
        await _run(cog, ctx)
    ctx.reply.assert_awaited_once_with("Ad quota already met this hour.")
    ctx.channel.start_commercial.assert_not_awaited()


async def test_quota_met_with_arg(cog, ad_manager, session):
    ad_manager.get_remaining = AsyncMock(return_value=0)
    ctx = _ctx("!ad 1")
    with patch(f"{_MOD}.get_active_session", AsyncMock(return_value=session)):
        await _run(cog, ctx)
    ctx.reply.assert_awaited_once_with("Ad quota already met this hour.")


async def test_runs_full_remaining_when_no_arg(cog, ad_manager, session):
    ctx = _ctx("!ad")
    with patch(f"{_MOD}.get_active_session", AsyncMock(return_value=session)), \
         patch(f"{_MOD}.clamp_to_ad_duration", return_value=180) as clamp:
        await _run(cog, ctx)
    clamp.assert_called_once_with(180)
    ctx.channel.start_commercial.assert_awaited_once_with(length=180)
    ad_manager.log_ad.assert_awaited_once()
    ad_manager.cancel_pending.assert_called_once()


async def test_requested_clamped_to_remaining(cog, ad_manager, session):
    # remaining=180, requested=600 → clamp called with min(600,180)=180
    ctx = _ctx("!ad 10")
    with patch(f"{_MOD}.get_active_session", AsyncMock(return_value=session)), \
         patch(f"{_MOD}.clamp_to_ad_duration", return_value=180) as clamp:
        await _run(cog, ctx)
    clamp.assert_called_once_with(180)


async def test_start_commercial_failure_replies(cog, ad_manager, session):
    ctx = _ctx("!ad")
    ctx.channel.start_commercial = AsyncMock(side_effect=Exception("twitch down"))
    with patch(f"{_MOD}.get_active_session", AsyncMock(return_value=session)):
        await _run(cog, ctx)
    assert "Failed to run ad" in ctx.reply.call_args.args[0]
    ad_manager.release_fire.assert_called_once()  # reservation freed for a retry
    ad_manager.log_ad.assert_not_awaited()


async def test_dedup_skips_when_ad_just_fired(cog, ad_manager, session):
    ad_manager.try_reserve_fire = MagicMock(return_value=False)
    ctx = _ctx("!ad")
    with patch(f"{_MOD}.get_active_session", AsyncMock(return_value=session)):
        await _run(cog, ctx)
    ctx.channel.start_commercial.assert_not_awaited()
    ad_manager.log_ad.assert_not_awaited()
    assert "just ran" in ctx.reply.call_args.args[0]


async def test_cancel_pending_before_fire(cog, ad_manager, session):
    """Manual !ad must cancel a scheduled auto-ad before calling Twitch."""
    calls = []
    ad_manager.cancel_pending = MagicMock(side_effect=lambda: calls.append("cancel"))
    ctx = _ctx("!ad")
    ctx.channel.start_commercial = AsyncMock(side_effect=lambda **_: calls.append("fire"))
    with patch(f"{_MOD}.get_active_session", AsyncMock(return_value=session)):
        await _run(cog, ctx)
    assert calls == ["cancel", "fire"]


async def test_twitch_429_replies_cooldown(cog, ad_manager, session):
    from twitchio.exceptions import HTTPException
    ctx = _ctx("!ad")
    ctx.channel.start_commercial = AsyncMock(
        side_effect=HTTPException("nope", status=429, extra={"retry_after": 120})
    )
    with patch(f"{_MOD}.get_active_session", AsyncMock(return_value=session)):
        await _run(cog, ctx)
    msg = ctx.reply.call_args.args[0]
    assert "cooldown" in msg and "2 min" in msg
    ad_manager.release_fire.assert_called_once()
    ad_manager.log_ad.assert_not_awaited()
