# couchd/platforms/twitch/components/cockpit.py
"""Dispatch messages/commands typed in veil's streamer cockpit into the bot.

The cockpit lets the streamer talk to chat (or run a command) without typing in
Twitch chat. Plain text is sent as the bot. A command is dispatched straight
into its registered callback with a synthetic, broadcaster-level context — the
bot ignores its own chat, so re-sending wouldn't trigger anything.

Commands that need real twitchio API objects (ads, shoutouts, clips) can't run
through a synthetic context, so they're refused with a chat notice.
"""
import logging
from dataclasses import dataclass

from couchd.core.config import settings
from couchd.platforms.twitch.components.utils import send_chat_message

log = logging.getLogger(__name__)

COMMAND_PREFIX = "!"
# Need a real broadcaster/PartialUser from twitchio — not available off-chat.
UNSUPPORTED_COMMANDS = {"ad", "so", "clip"}


@dataclass
class _CockpitAuthor:
    """Duck-typed twitchio Chatter — the streamer, with full privileges."""
    id: str
    name: str = "streamer"
    display_name: str = "streamer"

    @property
    def broadcaster(self) -> bool:
        return True

    @property
    def moderator(self) -> bool:
        return True


@dataclass
class _CockpitContext:
    """Duck-typed twitchio commands.Context for cockpit-issued commands."""
    content: str
    author: _CockpitAuthor
    _bot: object

    async def reply(self, text: str) -> None:
        await send_chat_message(self._bot, text)

    async def send(self, text: str) -> None:
        await send_chat_message(self._bot, text)


async def handle_send(bot, text: str) -> None:
    """Send a plain message, or dispatch a command, to Twitch from the cockpit."""
    text = text.strip()
    if not text:
        return

    if not text.startswith(COMMAND_PREFIX):
        await send_chat_message(bot, text)
        return

    cmd_name = text[len(COMMAND_PREFIX):].split(maxsplit=1)[0].lower()
    if cmd_name in UNSUPPORTED_COMMANDS:
        await send_chat_message(bot, f"⚠️ !{cmd_name} can't be run from the cockpit — use Twitch chat.")
        return

    command = bot.get_command(cmd_name)
    if command is None:
        log.info("Cockpit command !%s is not a known Twitch command.", cmd_name)
        return

    ctx = _CockpitContext(
        content=text,
        author=_CockpitAuthor(id=settings.TWITCH_OWNER_ID),
        _bot=bot,
    )
    try:
        await command.callback(command.component, ctx)
        log.info("Ran cockpit command !%s", cmd_name)
    except Exception:
        log.error("Cockpit command !%s failed", cmd_name, exc_info=True)
