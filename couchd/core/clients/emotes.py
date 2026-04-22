# couchd/core/clients/emotes.py
import asyncio
import logging

import aiohttp

log = logging.getLogger(__name__)


class EmoteClient:
    async def fetch_all(self, channel: str, channel_id: str) -> dict[str, str]:
        results = await asyncio.gather(
            self._fetch_7tv_global(),
            self._fetch_7tv_channel(channel_id),
            self._fetch_bttv_global(),
            self._fetch_bttv_channel(channel_id),
            self._fetch_ffz_global(),
            self._fetch_ffz_channel(channel),
            return_exceptions=True,
        )
        emotes: dict[str, str] = {}
        for result in results:
            if isinstance(result, dict):
                emotes.update(result)
        return emotes

    async def _fetch_7tv_global(self) -> dict[str, str]:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get("https://7tv.io/v3/emote-sets/global") as resp:
                    if resp.status != 200:
                        return {}
                    d = await resp.json()
            return self._parse_7tv(d.get("emotes", []))
        except Exception:
            return {}

    async def _fetch_7tv_channel(self, channel_id: str) -> dict[str, str]:
        if not channel_id:
            return {}
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"https://7tv.io/v3/users/twitch/{channel_id}") as resp:
                    if resp.status != 200:
                        return {}
                    d = await resp.json()
            return self._parse_7tv(d.get("emote_set", {}).get("emotes", []))
        except Exception:
            return {}

    async def _fetch_bttv_global(self) -> dict[str, str]:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get("https://api.betterttv.net/3/cached/emotes/global") as resp:
                    if resp.status != 200:
                        return {}
                    d = await resp.json()
            return self._parse_bttv(d if isinstance(d, list) else [])
        except Exception:
            return {}

    async def _fetch_bttv_channel(self, channel_id: str) -> dict[str, str]:
        if not channel_id:
            return {}
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"https://api.betterttv.net/3/cached/users/twitch/{channel_id}"
                ) as resp:
                    if resp.status != 200:
                        return {}
                    d = await resp.json()
            result = {}
            result.update(self._parse_bttv(d.get("channelEmotes", [])))
            result.update(self._parse_bttv(d.get("sharedEmotes", [])))
            return result
        except Exception:
            return {}

    async def _fetch_ffz_global(self) -> dict[str, str]:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get("https://api.frankerfacez.com/v1/set/global") as resp:
                    if resp.status != 200:
                        return {}
                    d = await resp.json()
            result = {}
            for set_id in d.get("default_sets", []):
                result.update(self._parse_ffz_set(d.get("sets", {}).get(str(set_id), {})))
            return result
        except Exception:
            return {}

    async def _fetch_ffz_channel(self, channel: str) -> dict[str, str]:
        if not channel:
            return {}
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"https://api.frankerfacez.com/v1/room/{channel}") as resp:
                    if resp.status != 200:
                        return {}
                    d = await resp.json()
            result = {}
            for s in d.get("sets", {}).values():
                result.update(self._parse_ffz_set(s))
            return result
        except Exception:
            return {}

    @staticmethod
    def _parse_7tv(emotes: list) -> dict[str, str]:
        result = {}
        for emote in emotes:
            host = (emote.get("data") or {}).get("host")
            if not host:
                continue
            files = host.get("files") or []
            file = next((f for f in files if f.get("name", "").startswith("2x")), files[0] if files else None)
            if not file:
                continue
            result[emote["name"]] = "https:" + host["url"] + file["name"]
        return result

    @staticmethod
    def _parse_bttv(emotes: list) -> dict[str, str]:
        result = {}
        for emote in emotes:
            code = emote.get("code")
            eid = emote.get("id")
            if not code or not eid:
                continue
            ext = emote.get("imageType", "png")
            result[code] = f"https://cdn.betterttv.net/emote/{eid}/2x.{ext}"
        return result

    @staticmethod
    def _parse_ffz_set(set_data: dict) -> dict[str, str]:
        result = {}
        for emote in set_data.get("emoticons", []):
            name = emote.get("name")
            urls = emote.get("urls") or {}
            if not name or not urls:
                continue
            url = urls.get("2") or urls.get("1")
            if url:
                result[name] = "https:" + url if url.startswith("//") else url
        return result
