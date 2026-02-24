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


class TwitchAdDuration(int, Enum):
    # Maps user-friendly numbers to Twitch allowed durations (30, 60, 90, 120, 150, 180)
    SHORT = 30
    ONE_MIN = 60
    ONE_POINT_FIVE = 90
    TWO_MIN = 120
    TWO_POINT_FIVE = 150
    THREE_MIN = 180


class BrandColors:
    # Use discord.Color objects for easy integration with Embeds
    PRIMARY = discord.Color.brand_green()
    TWITCH = discord.Color.purple()
    YOUTUBE = discord.Color.red()
    ERROR = discord.Color.brand_red()
    SUCCESS = discord.Color.green()
