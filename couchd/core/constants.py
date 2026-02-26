# couchd/core/constants.py
from enum import Enum
import discord
from dataclasses import dataclass


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


class AdConfig:
    WINDOW_SECONDS = 3600  # 60-minute rolling window
    WARNING_SECONDS = 60  # warn N seconds before auto-ad fires
    MIN_STREAM_AGE_SECONDS = 5 * 60  # don't auto-ad in first 5 min


class LeetCodeConfig:
    GRAPHQL_URL = "https://leetcode.com/graphql"
    SUBMISSION_URL = "https://leetcode.com/submissions/detail/{}/"


class ZerotracConfig:
    RATINGS_URL = "https://raw.githubusercontent.com/zerotrac/leetcode_problem_rating/main/ratings.txt"


class ChatMetrics:
    VELOCITY_WINDOW_MINUTES = 2
    HIGH_VELOCITY_THRESHOLD = 20  # msgs/min


class GitHubConfig:
    API_BASE = "https://api.github.com/repos"


class YouTubeConfig:
    RSS_URL = "https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
    VIDEO_URL = "https://www.youtube.com/watch?v="


@dataclass(frozen=True)
class Cooldown:
    user_seconds: int  # how long before the same user can run it again
    global_seconds: int  # how long before anyone in chat can run it again


class CommandCooldowns:
    COMMANDS = Cooldown(user_seconds=60, global_seconds=30)
    NEWVIDEO = Cooldown(user_seconds=120, global_seconds=60)
    LC = Cooldown(user_seconds=15, global_seconds=5)
    PROJECT = Cooldown(user_seconds=15, global_seconds=5)


class BotConfig:
    USER_AGENT = "BonelessCouchBot/1.0"


class ProblemsConfig:
    POLL_RATE_MINUTES: float = 1.0
    TAG_EASY = "Easy"
    TAG_MEDIUM = "Medium"
    TAG_HARD = "Hard"
    TITLE_MAX_LEN: int = 100


class BrandColors:
    # Use discord.Color objects for easy integration with Embeds
    PRIMARY = discord.Color.brand_green()
    TWITCH = discord.Color.purple()
    YOUTUBE = discord.Color.red()
    ERROR = discord.Color.brand_red()
    SUCCESS = discord.Color.green()
