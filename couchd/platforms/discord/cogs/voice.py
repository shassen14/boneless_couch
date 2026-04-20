import asyncio
import logging
import threading
import time

import discord
from discord.ext import commands, tasks

from couchd.core.clients import veil

log = logging.getLogger(__name__)

_SILENCE_S = 0.5  # seconds of no audio → stopped speaking


class SpeakingSink(discord.sinks.Sink):
    """Audio sink that detects speaking via presence/absence of audio packets."""

    def __init__(self, loop: asyncio.AbstractEventLoop, on_speaking) -> None:
        super().__init__()
        self._loop = loop
        self._on_speaking = on_speaking
        self._lock = threading.Lock()
        self._active: set[int] = set()
        self._last_audio: dict[int, float] = {}
        self._users: dict[int, discord.Member] = {}

    # Called from voice reader thread — must be thread-safe
    def write(self, data, user: discord.Member) -> None:
        uid = user.id
        with self._lock:
            self._last_audio[uid] = time.monotonic()
            self._users[uid] = user
            if uid not in self._active:
                self._active.add(uid)
                asyncio.run_coroutine_threadsafe(
                    self._on_speaking(user, True), self._loop
                )

    def drain_silent(self) -> list[discord.Member]:
        """Remove and return members who have gone silent. Called from event loop."""
        now = time.monotonic()
        stopped: list[discord.Member] = []
        with self._lock:
            for uid in list(self._active):
                if now - self._last_audio.get(uid, now) >= _SILENCE_S:
                    self._active.discard(uid)
                    if user := self._users.get(uid):
                        stopped.append(user)
        return stopped

    def cleanup(self) -> None:
        with self._lock:
            self._active.clear()
            self._last_audio.clear()
            self._users.clear()


class VoiceWatcherCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._voice_clients: dict[int, discord.VoiceClient] = {}
        self._sinks: dict[int, SpeakingSink] = {}

    async def cog_load(self) -> None:
        self._silence_poll.start()
        if self.bot.is_ready():
            await self._scan_channels()

    def cog_unload(self) -> None:
        self._silence_poll.cancel()
        for cid in list(self._voice_clients):
            asyncio.ensure_future(self._disconnect(cid))

    @tasks.loop(seconds=0.1)
    async def _silence_poll(self) -> None:
        for sink in list(self._sinks.values()):
            for user in sink.drain_silent():
                await veil.post_event("discord.voice.speaking", {
                    "user_id": str(user.id),
                    "username": user.name,
                    "speaking": False,
                })

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        await self._scan_channels()

    async def _scan_channels(self) -> None:
        for guild in self.bot.guilds:
            for channel in guild.voice_channels:
                if any(not m.bot for m in channel.members):
                    await self._connect(channel)

    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ) -> None:
        if member.bot:
            return

        joined = before.channel is None and after.channel is not None
        left = before.channel is not None and after.channel is None

        if joined:
            await veil.post_event("discord.voice.join", {
                "user_id": str(member.id),
                "username": member.name,
                "display_name": member.display_name,
                "avatar_url": str(member.display_avatar.url),
                "channel_id": str(after.channel.id),
                "channel_name": after.channel.name,
            })
            await self._connect(after.channel)
            return

        if left:
            await veil.post_event("discord.voice.leave", {
                "user_id": str(member.id),
                "username": member.name,
                "channel_id": str(before.channel.id),
            })
            if not any(not m.bot for m in before.channel.members):
                await self._disconnect(before.channel.id)
            return

        if before.self_mute != after.self_mute or before.self_deaf != after.self_deaf:
            await veil.post_event("discord.voice.mute", {
                "user_id": str(member.id),
                "self_mute": after.self_mute,
                "self_deaf": after.self_deaf,
            })

    async def _connect(self, channel: discord.VoiceChannel) -> None:
        if channel.id in self._voice_clients:
            return
        try:
            loop = asyncio.get_running_loop()
            vc = await channel.connect()
            sink = SpeakingSink(loop, self._on_speaking)
            vc.start_recording(sink, self._after_recording)
            self._voice_clients[channel.id] = vc
            self._sinks[channel.id] = sink
        except Exception:
            log.warning("Failed to connect to voice channel %s", channel.name, exc_info=True)

    async def _disconnect(self, channel_id: int) -> None:
        vc = self._voice_clients.pop(channel_id, None)
        sink = self._sinks.pop(channel_id, None)
        if vc:
            try:
                vc.stop_recording()
                await vc.disconnect()
            except Exception:
                log.warning("Error disconnecting voice", exc_info=True)
        if sink:
            sink.cleanup()

    async def _on_speaking(self, user: discord.Member, speaking: bool) -> None:
        await veil.post_event("discord.voice.speaking", {
            "user_id": str(user.id),
            "username": user.name,
            "speaking": speaking,
        })

    async def _after_recording(self, sink, channel, *args) -> None:
        pass


def setup(bot: commands.Bot) -> None:
    bot.add_cog(VoiceWatcherCog(bot))
