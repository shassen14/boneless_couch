# couchd/core/moderation.py
import re
from dataclasses import dataclass, field


@dataclass
class PendingMessage:
    message_id: str
    payload: dict
    hold_sources: list[str] = field(default_factory=list)


class ModerationEngine:
    def __init__(self, patterns: list[str]):
        self._regexes = [re.compile(p, re.IGNORECASE) for p in patterns]
        self._pending: dict[str, PendingMessage] = {}

    def is_flagged(self, text: str) -> bool:
        return any(r.search(text) for r in self._regexes)

    def add_pending(self, message_id: str, payload: dict, source: str) -> PendingMessage:
        msg = PendingMessage(message_id=message_id, payload=payload, hold_sources=[source])
        self._pending[message_id] = msg
        return msg

    def add_hold_source(self, message_id: str, source: str) -> PendingMessage | None:
        msg = self._pending.get(message_id)
        if msg and source not in msg.hold_sources:
            msg.hold_sources.append(source)
        return msg

    def pop(self, message_id: str) -> PendingMessage | None:
        return self._pending.pop(message_id, None)

    def has(self, message_id: str) -> bool:
        return message_id in self._pending

    def get(self, message_id: str) -> PendingMessage | None:
        return self._pending.get(message_id)
