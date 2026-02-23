# couchd/core/constants.py
from enum import Enum
import discord


class Platform(str, Enum):
    TWITCH = "twitch"
    YOUTUBE = "youtube"


class StreamDefaults(str, Enum):
    TITLE = "No Title Provided"
    CATEGORY = "Just Chatting"


class TwitchConfig:
    THUMBNAIL_WIDTH = "1280"
    THUMBNAIL_HEIGHT = "720"
    THUMBNAIL_PLACEHOLDER_W = "{width}"
    THUMBNAIL_PLACEHOLDER_H = "{height}"
    BASE_URL = "https://twitch.tv/"


class BrandColors:
    # Use discord.Color objects for easy integration with Embeds
    PRIMARY = discord.Color.brand_green()
    TWITCH = discord.Color.purple()
    YOUTUBE = discord.Color.red()
    ERROR = discord.Color.brand_red()
    SUCCESS = discord.Color.green()
