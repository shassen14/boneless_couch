"""
Moved away because doesn't use pytest
tests/integration/test_observability.py

Fires a test ERROR log and a test Sentry event to verify both observability
channels are wired up correctly. Run this on the Pi after deploying.

Usage:
    docker compose run --rm discord python tests/integration/test_observability.py
"""

import logging
import sentry_sdk
from couchd.core.config import settings
from couchd.core.constants import BotConfig
from couchd.core.logger import setup_logging

setup_logging(webhook_url=settings.BOT_LOGS_WEBHOOK_URL, bot_name="test")
log = logging.getLogger(__name__)

print("--- Observability Test ---")

# --- Discord Webhook ---
if not settings.BOT_LOGS_WEBHOOK_URL:
    print("[webhook] SKIP — BOT_LOGS_WEBHOOK_URL not set")
else:
    print("[webhook] POSTing test embed to Discord...")
    import json
    import urllib.error
    import urllib.request

    payload = {
        "embeds": [
            {
                "title": "[test] Observability check",
                "description": "**Webhook is working** — sent from `tests/integration/test_observability.py`",
                "color": 0xFF4500,
            }
        ]
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        settings.BOT_LOGS_WEBHOOK_URL,
        data=data,
        headers={
            "Content-Type": "application/json",
            "User-Agent": BotConfig.USER_AGENT,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            print(f"[webhook] Done — HTTP {resp.status} — check #bot-logs")
    except urllib.error.HTTPError as e:
        print(f"[webhook] FAILED — HTTP {e.code}: {e.read().decode()}")
    except Exception as e:
        print(f"[webhook] FAILED — {e}")

# --- Sentry ---
if not settings.SENTRY_DSN:
    print("[sentry]  SKIP — SENTRY_DSN not set")
else:
    sentry_sdk.init(dsn=settings.SENTRY_DSN)
    print("[sentry]  Sending test message to Sentry...")
    sentry_sdk.capture_message("Observability check: Sentry is working", level="error")
    sentry_sdk.flush(timeout=5)
    print("[sentry]  Done — check your Sentry project's Issues tab")

print("--- Done ---")
