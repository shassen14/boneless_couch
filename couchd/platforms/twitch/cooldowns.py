# couchd/platforms/twitch/cooldowns.py
import time
import logging
from couchd.core.constants import Cooldown

log = logging.getLogger(__name__)


class CooldownManager:
    """
    Tracks per-user and global (channel-wide) cooldowns for chat commands.

    Both cooldowns must be clear for a command to proceed.
    Global cooldown prevents chat spam regardless of who is asking.
    User cooldown prevents a single viewer from hammering a command.
    """

    def __init__(self):
        self._user_last: dict[str, dict[str, float]] = {}  # cmd -> {user_id -> timestamp}
        self._global_last: dict[str, float] = {}           # cmd -> timestamp

    def check(self, cmd: str, user_id: str, cooldown: Cooldown) -> bool:
        """Returns True if the command is on cooldown and should be silently blocked."""
        now = time.monotonic()

        if now - self._global_last.get(cmd, 0.0) < cooldown.global_seconds:
            return True

        if now - self._user_last.get(cmd, {}).get(user_id, 0.0) < cooldown.user_seconds:
            return True

        return False

    def record(self, cmd: str, user_id: str) -> None:
        """Mark a command as just used by this user."""
        now = time.monotonic()
        self._global_last[cmd] = now
        self._user_last.setdefault(cmd, {})[user_id] = now
