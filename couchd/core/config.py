# couchd/core/config.py

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Manages all application settings.
    Loads variables from a .env file and validates them.
    """

    # This tells Pydantic to look for a .env file in our project root.
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
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


# Create a single, importable instance of our settings.
# This instance will be created only once when the module is first imported.
settings = Settings()
