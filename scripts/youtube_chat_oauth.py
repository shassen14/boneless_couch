# scripts/youtube_chat_oauth.py
"""
One-time OAuth flow for the YouTube Live Chat bot.
Run this once to generate the token file, then the bot will auto-refresh it.

Usage:
    uv run python scripts/youtube_chat_oauth.py
"""
import pickle
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow

from couchd.core.config import settings
from couchd.core.constants import YouTubeChatConfig


def main():
    if not settings.YOUTUBE_CLIENT_SECRET_FILE:
        raise RuntimeError("Set YOUTUBE_CLIENT_SECRET_FILE in your .env first.")

    secret_path = Path(settings.YOUTUBE_CLIENT_SECRET_FILE)
    if not secret_path.exists():
        raise FileNotFoundError(f"Client secret file not found: {secret_path}")

    token_path = Path(settings.YOUTUBE_CHAT_TOKEN_FILE)

    print(f"Opening browser for YouTube OAuth...")
    print(f"Scopes: {YouTubeChatConfig.SCOPES}")

    flow = InstalledAppFlow.from_client_secrets_file(str(secret_path), YouTubeChatConfig.SCOPES)
    creds = flow.run_local_server(port=0)

    with token_path.open("wb") as f:
        pickle.dump(creds, f)

    print(f"Token saved to: {token_path}")
    print("YouTube chat bot is authorized. You can now run the bot.")


if __name__ == "__main__":
    main()
