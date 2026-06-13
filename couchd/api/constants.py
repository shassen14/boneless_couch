# couchd/api/constants.py
"""Constants for the content_os read API. No magic strings in route/serializer code."""
from enum import Enum


class ApiConfig:
    """Server-level constants for the read API."""

    ROUTE_PREFIX = "/api/v1"
    AUTH_SCHEME = "Bearer"
    AUTH_HEADER = "Authorization"
    DEFAULT_SESSION_LIMIT = 50
    MAX_SESSION_LIMIT = 200


class MarkerField(str, Enum):
    """Keys in a serialized marker object (the /markers response items)."""

    ID = "id"
    EVENT_TYPE = "event_type"
    TIMESTAMP = "timestamp"
    VOD_TIMESTAMP = "vod_timestamp"
    ABSOLUTE_SECONDS = "absolute_seconds"
    NOTES = "notes"
    DETAIL = "detail"


class SessionField(str, Enum):
    """Keys in a serialized session object."""

    ID = "id"
    PLATFORM = "platform"
    TITLE = "title"
    CATEGORY = "category"
    VOD_URL = "vod_url"
    PEAK_VIEWERS = "peak_viewers"
    START_TIME = "start_time"
    END_TIME = "end_time"
    DURATION_SECONDS = "duration_seconds"
    IS_ACTIVE = "is_active"


class RecapField(str, Enum):
    """Keys in the recap response."""

    SESSION_ID = "session_id"
    TITLE = "title"
    DURATION_SECONDS = "duration_seconds"
    PEAK_VIEWERS = "peak_viewers"
    PROBLEMS = "problems"
    PROJECTS = "projects"
    CLIP_COUNT = "clip_count"
