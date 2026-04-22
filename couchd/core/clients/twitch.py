# couchd/core/clients/twitch.py
import aiohttp
import logging

from couchd.core.config import settings

log = logging.getLogger(__name__)


class TwitchClient:
    """
    A reusable async client for interacting with the Twitch API.
    Handles automatic App Access Token generation and stream polling.
    """

    def __init__(self):
        self.client_id = settings.TWITCH_CLIENT_ID
        self.client_secret = settings.TWITCH_CLIENT_SECRET
        self.app_token = None

    async def _get_app_token(self) -> str:
        """Fetches a new App Access Token from Twitch."""
        url = f"https://id.twitch.tv/oauth2/token?client_id={self.client_id}&client_secret={self.client_secret}&grant_type=client_credentials"

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url) as response:
                    if response.status == 200:
                        data = await response.json()
                        self.app_token = data.get("access_token")
                        log.info("Successfully acquired Twitch App Access Token.")
                        return self.app_token
                    else:
                        log.error(
                            f"Failed to get Twitch token: {response.status} - {await response.text()}"
                        )
                        return None
        except Exception as e:
            log.error("Exception while fetching Twitch token", exc_info=e)
            return None

    async def get_stream_status(self, username: str) -> dict | None:
        """
        Checks if a user is live.
        Returns the stream data dict if live, or None if offline/error.
        """
        if not self.app_token:
            await self._get_app_token()

        if not self.app_token:
            return None  # Couldn't get a token

        url = f"https://api.twitch.tv/helix/streams?user_login={username}"
        headers = {
            "Client-ID": self.client_id,
            "Authorization": f"Bearer {self.app_token}",
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers) as response:
                    # If token expired (401), get a new one and retry once
                    if response.status == 401:
                        log.warning("Twitch token expired. Refreshing...")
                        await self._get_app_token()
                        headers["Authorization"] = f"Bearer {self.app_token}"
                        async with session.get(url, headers=headers) as retry_response:
                            if retry_response.status == 200:
                                data = await retry_response.json()
                            else:
                                return None
                    elif response.status == 200:
                        data = await response.json()
                    else:
                        log.error(f"Twitch API Error: {response.status}")
                        return None

            # If the 'data' list has items, the user is live!
            if data and data.get("data"):
                return data["data"][0]  # Return the first stream object

            return None  # List is empty, user is offline

        except aiohttp.ClientError as e:
            log.error("Network error checking Twitch stream status", exc_info=e)
            raise
        except Exception as e:
            log.error("Exception while checking Twitch stream status", exc_info=e)
            return None

    async def get_user_id(self, username: str) -> str | None:
        """Fetches the Twitch user ID for a given username. Returns the ID string or None."""
        if not self.app_token:
            await self._get_app_token()

        if not self.app_token:
            return None

        url = f"https://api.twitch.tv/helix/users?login={username}"
        headers = {
            "Client-ID": self.client_id,
            "Authorization": f"Bearer {self.app_token}",
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers) as response:
                    if response.status == 401:
                        log.warning("Twitch token expired. Refreshing...")
                        await self._get_app_token()
                        headers["Authorization"] = f"Bearer {self.app_token}"
                        async with session.get(url, headers=headers) as retry_response:
                            if retry_response.status == 200:
                                data = await retry_response.json()
                            else:
                                return None
                    elif response.status == 200:
                        data = await response.json()
                    else:
                        log.error(f"Twitch API Error: {response.status}")
                        return None

            if data and data.get("data"):
                return data["data"][0]["id"]

            return None

        except Exception as e:
            log.error("Exception while fetching Twitch user ID", exc_info=e)
            return None

    async def get_global_emotes(self) -> dict[str, str]:
        """Fetches Twitch global emotes. Returns {name: url} or {} on error."""
        if not self.app_token:
            await self._get_app_token()
        if not self.app_token:
            return {}

        url = "https://api.twitch.tv/helix/chat/emotes/global"
        headers = {
            "Client-ID": self.client_id,
            "Authorization": f"Bearer {self.app_token}",
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers) as response:
                    if response.status == 401:
                        log.warning("Twitch token expired. Refreshing...")
                        await self._get_app_token()
                        headers["Authorization"] = f"Bearer {self.app_token}"
                        async with session.get(url, headers=headers) as retry:
                            if retry.status == 200:
                                data = await retry.json()
                            else:
                                return {}
                    elif response.status == 200:
                        data = await response.json()
                    else:
                        log.error(f"Twitch API Error: {response.status}")
                        return {}

            return {
                e["name"]: f"https://static-cdn.jtvnw.net/emoticons/v2/{e['id']}/default/dark/2.0"
                for e in data.get("data", [])
            }
        except Exception:
            log.error("Exception while fetching Twitch global emotes", exc_info=True)
            return {}

    async def get_channel_emotes(self, broadcaster_id: str) -> dict[str, str]:
        """Fetches emotes for a specific channel. Returns {name: url} or {} on error."""
        if not broadcaster_id:
            return {}
        if not self.app_token:
            await self._get_app_token()
        if not self.app_token:
            return {}

        url = f"https://api.twitch.tv/helix/chat/emotes?broadcaster_id={broadcaster_id}"
        headers = {
            "Client-ID": self.client_id,
            "Authorization": f"Bearer {self.app_token}",
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers) as response:
                    if response.status == 401:
                        log.warning("Twitch token expired. Refreshing...")
                        await self._get_app_token()
                        headers["Authorization"] = f"Bearer {self.app_token}"
                        async with session.get(url, headers=headers) as retry:
                            if retry.status == 200:
                                data = await retry.json()
                            else:
                                return {}
                    elif response.status == 200:
                        data = await response.json()
                    else:
                        log.error(f"Twitch API Error: {response.status}")
                        return {}

            return {
                e["name"]: f"https://static-cdn.jtvnw.net/emoticons/v2/{e['id']}/default/dark/2.0"
                for e in data.get("data", [])
            }
        except Exception:
            log.error("Exception while fetching Twitch channel emotes", exc_info=True)
            return {}

    async def get_clip(self, clip_id: str) -> dict | None:
        """Fetches clip metadata from Twitch. Returns the clip object or None."""
        if not self.app_token:
            await self._get_app_token()

        if not self.app_token:
            return None

        url = f"https://api.twitch.tv/helix/clips?id={clip_id}"
        headers = {
            "Client-ID": self.client_id,
            "Authorization": f"Bearer {self.app_token}",
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers) as response:
                    if response.status == 401:
                        log.warning("Twitch token expired. Refreshing...")
                        await self._get_app_token()
                        headers["Authorization"] = f"Bearer {self.app_token}"
                        async with session.get(url, headers=headers) as retry_response:
                            if retry_response.status == 200:
                                data = await retry_response.json()
                            else:
                                return None
                    elif response.status == 200:
                        data = await response.json()
                    else:
                        log.error(f"Twitch API Error: {response.status}")
                        return None

            if data and data.get("data"):
                return data["data"][0]

            return None

        except Exception as e:
            log.error("Exception while fetching Twitch clip", exc_info=e)
            return None
