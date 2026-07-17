# tests/unit/platforms/twitch/test_ad_messages.py
from unittest.mock import patch

from couchd.platforms.twitch.ads import messages


def test_pick_ad_message_returns_none_when_chance_fails():
    with patch("random.random", return_value=0.99):
        assert messages.pick_ad_message() is None


def test_pick_ad_message_returns_static_when_no_video():
    with patch("random.random", return_value=0.0):
        msg = messages.pick_ad_message(None)
    assert msg in messages._STATIC_POOL


def test_pick_ad_message_can_include_latest_video():
    video = {"title": "My Build", "video_url": "https://youtu.be/x"}
    with patch("random.random", return_value=0.0), \
         patch("random.choice", side_effect=lambda pool: pool[-1]):
        msg = messages.pick_ad_message(video)
    assert "My Build" in msg
    assert "https://youtu.be/x" in msg


def test_pick_ad_message_video_not_in_static_pool_branch():
    # When the chosen index lands on a static message, video is unused but valid.
    video = {"title": "T", "video_url": "U"}
    with patch("random.random", return_value=0.0), \
         patch("random.choice", side_effect=lambda pool: pool[0]):
        msg = messages.pick_ad_message(video)
    assert msg == messages._STATIC_POOL[0]


def test_pick_return_message_always_returns_from_pool():
    for _ in range(20):
        assert messages.pick_return_message() in messages._RETURN_POOL
