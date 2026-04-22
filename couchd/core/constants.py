# couchd/core/constants.py
from enum import Enum
import discord
from dataclasses import dataclass


class EventType(str, Enum):
    PROBLEM_ATTEMPT = "problem_attempt"
    PROJECT = "project"
    GAME = "game"
    EDIT = "edit"
    TOPIC = "topic"
    TASK = "task"


class InteractionType(str, Enum):
    FOLLOW    = "follow"
    SUB       = "sub"
    RESUB     = "resub"
    GIFTBOMB  = "giftbomb"
    BITS      = "bits"
    RAID      = "raid"


TASK_DONE = "done"

MACRO_EVENT_TYPES = frozenset({
    EventType.PROBLEM_ATTEMPT,
    EventType.PROJECT,
    EventType.GAME,
    EventType.EDIT,
    EventType.TOPIC,
})


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
    # WINDOW_SECONDS is computed per-instance in AdBudgetManager as 3600 + required_seconds,
    # because Twitch's cooldown is 60 min starting AFTER the ad ends (e.g. 3-min ad = 63-min window).
    WARNING_SECONDS = 60  # warn N seconds before mid-stream auto-ad fires
    MIN_STREAM_AGE_SECONDS = 5 * 60  # delay before fallback opener check
    OPENER_DELAY_SECONDS = 30  # wait for StreamSession to be created before opener ad fires


class LeetCodeConfig:
    BASE_URL = "https://leetcode.com"
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
    CLIP = Cooldown(user_seconds=120, global_seconds=30)
    IDEA = Cooldown(user_seconds=30, global_seconds=10)
    SIMPLE = Cooldown(user_seconds=15, global_seconds=5)


class ClipConfig:
    DURATION = 30
    URL_BASE = "https://clips.twitch.tv/"
    DEFAULT_TITLE = "No context provided. Just vibes. ✨"


class BotConfig:
    USER_AGENT = "BonelessCouchBot/1.0"


class ProblemsConfig:
    POLL_RATE_MINUTES: float = 1.0
    TAG_EASY = "Easy"
    TAG_MEDIUM = "Medium"
    TAG_HARD = "Hard"
    TITLE_MAX_LEN: int = 100


class StatusConfig:
    POLL_RATE_MINUTES: int = 5


class IdeaConfig:
    POLL_RATE_MINUTES: float = 1.0
    REACTION_SUPPORT = "✅"
    REACTION_AGAINST = "❌"


class HoldSource:
    BONELESS_COUCH = "boneless_couch"
    TWITCH_AUTOMOD = "twitch_automod"


class BrandColors:
    # Use discord.Color objects for easy integration with Embeds
    PRIMARY = discord.Color.brand_green()
    TWITCH = discord.Color.purple()
    YOUTUBE = discord.Color.red()
    ERROR = discord.Color.brand_red()
    SUCCESS = discord.Color.green()
