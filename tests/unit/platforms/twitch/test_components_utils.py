# tests/unit/platforms/twitch/test_components_utils.py
import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from couchd.core.constants import TwitchAdDuration
from couchd.platforms.twitch.components import utils

_MOD = "couchd.platforms.twitch.components.utils"


# ── clamp_to_ad_duration ──────────────────────────────────────────────────────

def test_clamp_returns_min_when_below_smallest():
    smallest = min(d.value for d in TwitchAdDuration)
    assert utils.clamp_to_ad_duration(0) == smallest
    assert utils.clamp_to_ad_duration(smallest - 1) == smallest


def test_clamp_returns_largest_valid_at_or_below():
    valid = sorted(d.value for d in TwitchAdDuration)
    # exactly on a boundary
    assert utils.clamp_to_ad_duration(valid[1]) == valid[1]
    # between two boundaries → rounds down
    between = valid[1] + 1
    assert utils.clamp_to_ad_duration(between) == valid[1]


def test_clamp_caps_at_max():
    largest = max(d.value for d in TwitchAdDuration)
    assert utils.clamp_to_ad_duration(10_000) == largest


# ── send_chat_message ─────────────────────────────────────────────────────────

async def test_send_chat_message_sends_to_channel():
    user = MagicMock()
    user.send_message = AsyncMock()
    bot = MagicMock()
    bot.fetch_users = AsyncMock(return_value=[user])

    await utils.send_chat_message(bot, "hello")
    user.send_message.assert_awaited_once()
    assert user.send_message.call_args.kwargs["message"] == "hello"


async def test_send_chat_message_no_user_is_noop():
    bot = MagicMock()
    bot.fetch_users = AsyncMock(return_value=[])
    await utils.send_chat_message(bot, "hello")  # must not raise


async def test_send_chat_message_swallows_errors():
    bot = MagicMock()
    bot.fetch_users = AsyncMock(side_effect=Exception("boom"))
    await utils.send_chat_message(bot, "hello")  # must not raise


# ── format_follow_age ─────────────────────────────────────────────────────────

def _ago(days: int):
    return datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days)


@pytest.mark.parametrize(
    "days, expected",
    [
        (0, "less than a day"),
        (1, "1 day"),
        (5, "5 days"),
        (30, "1 month"),
        (65, "2 months, 5 days"),
        (365, "1 year"),
        (400, "1 year, 1 month, 5 days"),
    ],
)
def test_format_follow_age(days, expected):
    assert utils.format_follow_age(_ago(days)) == expected
