# tests/unit/core/test_cooldowns.py
from unittest.mock import patch

import pytest

from couchd.core.constants import Cooldown
from couchd.core.cooldowns import CooldownManager

_COOLDOWN = Cooldown(user_seconds=15, global_seconds=5)
_CLOCK = "couchd.core.cooldowns.time.monotonic"


@pytest.fixture
def manager():
    return CooldownManager()


def test_first_use_not_blocked(manager):
    with patch(_CLOCK, return_value=100.0):
        assert manager.check("lc", "user1", _COOLDOWN) is False


def test_same_user_blocked_within_user_window(manager):
    with patch(_CLOCK, return_value=100.0):
        manager.record("lc", "user1")
    with patch(_CLOCK, return_value=110.0):  # 10s < 15s user window
        assert manager.check("lc", "user1", _COOLDOWN) is True


def test_same_user_allowed_after_user_window(manager):
    with patch(_CLOCK, return_value=100.0):
        manager.record("lc", "user1")
    with patch(_CLOCK, return_value=116.0):  # 16s > 15s user window, > global
        assert manager.check("lc", "user1", _COOLDOWN) is False


def test_other_user_blocked_by_global_window(manager):
    with patch(_CLOCK, return_value=100.0):
        manager.record("lc", "user1")
    with patch(_CLOCK, return_value=103.0):  # 3s < 5s global window
        assert manager.check("lc", "user2", _COOLDOWN) is True


def test_other_user_allowed_after_global_window(manager):
    with patch(_CLOCK, return_value=100.0):
        manager.record("lc", "user1")
    with patch(_CLOCK, return_value=106.0):  # 6s > 5s global, fresh user
        assert manager.check("lc", "user2", _COOLDOWN) is False


def test_cooldowns_are_per_command(manager):
    with patch(_CLOCK, return_value=100.0):
        manager.record("lc", "user1")
        # A different command for the same user is independent.
        assert manager.check("project", "user1", _COOLDOWN) is False
