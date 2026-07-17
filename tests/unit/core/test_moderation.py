# tests/unit/core/test_moderation.py
import pytest

from couchd.core.moderation import ModerationEngine


@pytest.fixture
def engine():
    return ModerationEngine([r"badword", r"https?://spam\."])


def test_is_flagged_matches_pattern(engine):
    assert engine.is_flagged("this contains a badword here") is True


def test_is_flagged_case_insensitive(engine):
    assert engine.is_flagged("BADWORD") is True


def test_is_flagged_clean_message(engine):
    assert engine.is_flagged("a perfectly nice message") is False


def test_add_pending_creates_entry_with_source(engine):
    msg = engine.add_pending("m1", {"text": "hi"}, "twitch_automod")

    assert engine.has("m1")
    assert msg.hold_sources == ["twitch_automod"]
    assert engine.get("m1").payload == {"text": "hi"}


def test_add_hold_source_appends_unique(engine):
    engine.add_pending("m1", {}, "twitch_automod")

    engine.add_hold_source("m1", "regex")
    engine.add_hold_source("m1", "regex")  # duplicate ignored

    assert engine.get("m1").hold_sources == ["twitch_automod", "regex"]


def test_add_hold_source_unknown_message_returns_none(engine):
    assert engine.add_hold_source("missing", "regex") is None


def test_pop_removes_and_returns(engine):
    engine.add_pending("m1", {}, "src")

    popped = engine.pop("m1")

    assert popped.message_id == "m1"
    assert not engine.has("m1")
    assert engine.pop("m1") is None  # popping again is a no-op
