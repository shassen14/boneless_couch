# couchd/platforms/twitch/components/timers.py
import asyncio
import logging

from couchd.core.config import settings
from couchd.core import socials
from couchd.core.utils import get_active_session
from couchd.platforms.twitch.components.utils import send_chat_message

log = logging.getLogger(__name__)


class ChatTimers:
    def __init__(self, bot):
        self._bot = bot
        self._messages = socials.timer_messages()
        self._index = 0

    def start(self) -> None:
        if not self._messages:
            log.info("ChatTimers: no social links configured — timers disabled.")
            return
        asyncio.create_task(self._run_loop())
        log.info(
            "ChatTimers: started with %d message(s), interval=%.0f min.",
            len(self._messages),
            settings.CHAT_TIMER_INTERVAL_MINUTES,
        )

    async def _run_loop(self) -> None:
        interval = settings.CHAT_TIMER_INTERVAL_MINUTES * 60
        while True:
            await asyncio.sleep(interval)
            try:
                if not await get_active_session():
                    continue
                msg = self._messages[self._index % len(self._messages)]
                self._index += 1
                await send_chat_message(self._bot, msg)
            except Exception:
                log.error("Error in Twitch chat timer loop", exc_info=True)
