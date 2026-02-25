# couchd/core/config.py

import pathlib
from pydantic_settings import BaseSettings, SettingsConfigDict

# Project root is 3 levels up from this file (couchd/core/config.py).
_PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
_ENV_PATH_FILE = _PROJECT_ROOT / ".env.path"

if not _ENV_PATH_FILE.exists():
    raise FileNotFoundError(
        f"Missing {_ENV_PATH_FILE}. "
        "Create it and put the absolute path to your .env file inside."
    )

_env_file = pathlib.Path(_ENV_PATH_FILE.read_text().strip())

if not _env_file.exists():
    raise FileNotFoundError(
        f".env file not found at '{_env_file}' (read from {_ENV_PATH_FILE}). "
        "Check that the path in .env.path is correct."
    )


class Settings(BaseSettings):
    """
    Manages all application settings.
    Loads variables from the .env file whose path is in .env.path.
    """

    model_config = SettingsConfigDict(
        env_file_encoding="utf-8", extra="ignore"
    )

    # Discord Bot Settings
    DISCORD_BOT_TOKEN: str

    # Twitch Bot Settings
    TWITCH_CLIENT_ID: str
    TWITCH_CLIENT_SECRET: str

    TWITCH_BOT_TOKEN: str
    TWITCH_BOT_ID: str

    TWITCH_OWNER_ID: str
    TWITCH_CHANNEL: str

    # Database Settings
    DB_USER: str
    DB_PASSWORD: str
    DB_HOST: str
    DB_PORT: int = 5432  # Default to 5432 if not specified
    DB_NAME: str

    # Configurable polling rate (defaults to 2 minutes if not in .env)
    TWITCH_POLL_RATE_MINUTES: float = 2.0

    # Ad budget: how many minutes of ads are required per hour
    TWITCH_AD_MINUTES_PER_HOUR: int = 3

    # YouTube (optional — omit to disable VideoWatcherCog)
    YOUTUBE_CHANNEL_ID: str | None = None
    YOUTUBE_POLL_RATE_MINUTES: float = 15.0

    # Social links (comma-separated; empty list disables /socials field)
    SOCIAL_TWITCH: list[str] = []
    SOCIAL_YOUTUBE: list[str] = []
    SOCIAL_GITHUB: list[str] = []

    # Observability (optional)
    SENTRY_DSN: str | None = None
    BOT_LOGS_WEBHOOK_URL: str | None = None


# Create a single, importable instance of our settings.
# This instance will be created only once when the module is first imported.
settings = Settings(_env_file=str(_env_file))
