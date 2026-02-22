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

    # --- Discord Bot Settings ---
    # We define the required environment variables here.
    # Pydantic will automatically read them from the .env file.
    # If DISCORD_BOT_TOKEN is not found in the .env file,
    # the program will raise a ValidationError on startup.
    DISCORD_BOT_TOKEN: str


# Create a single, importable instance of our settings.
# This instance will be created only once when the module is first imported.
settings = Settings()
