# tests/unit/platforms/twitch/test_welcome_messages.py
import pytest

from couchd.platforms.twitch.components import welcome_messages as wm


@pytest.mark.parametrize(
    "tier,expected",
    [("1000", "Tier 1"), ("2000", "Tier 2"), ("3000", "Tier 3"), (1000, "Tier 1")],
)
def test_tier_label_known(tier, expected):
    assert wm._tier_label(tier) == expected


def test_tier_label_unknown_falls_back():
    assert wm._tier_label("prime") == "Tier prime"


def test_follow_message_contains_name():
    for _ in range(20):
        assert "Couchster" in wm.follow_message("Couchster")


def test_sub_message_contains_name_and_tier_label():
    for _ in range(20):
        msg = wm.sub_message("Bob", "2000")
        assert "Bob" in msg
        assert "Tier 2" in msg


def test_resub_message_contains_months():
    for _ in range(20):
        msg = wm.resub_message("Ann", 7, "1000")
        assert "Ann" in msg
        assert "7" in msg
        assert "Tier 1" in msg


def test_giftbomb_message_contains_gifter_and_count():
    for _ in range(20):
        msg = wm.giftbomb_message("Santa", 10)
        assert "Santa" in msg
        assert "10" in msg


def test_bits_message_contains_name_and_bits():
    for _ in range(20):
        msg = wm.bits_message("Gem", 500)
        assert "Gem" in msg
        assert "500" in msg


def test_raid_message_contains_raider_and_count():
    for _ in range(20):
        msg = wm.raid_message("Captain", 42)
        assert "Captain" in msg
        assert "42" in msg


def test_tip_message_formats_amount_to_two_decimals():
    for _ in range(20):
        msg = wm.tip_message("Generous", 5, "USD")
        assert "Generous" in msg
        assert "5.00" in msg
        assert "USD" in msg
