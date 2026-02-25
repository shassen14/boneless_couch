"""
scripts/test_observability.py

Fires a test ERROR log and a test Sentry event to verify both observability
channels are wired up correctly. Run this on the Pi after deploying.

Usage:
    docker compose run --rm discord python scripts/test_observability.py
"""

import logging
import time
import sentry_sdk
from couchd.core.config import settings
from couchd.core.logger import setup_logging

setup_logging(webhook_url=settings.BOT_LOGS_WEBHOOK_URL, bot_name="test")
log = logging.getLogger(__name__)

print("--- Observability Test ---")

# --- Discord Webhook ---
if not settings.BOT_LOGS_WEBHOOK_URL:
    print("[webhook] SKIP — BOT_LOGS_WEBHOOK_URL not set")
else:
    print("[webhook] Firing test ERROR to Discord...")
    try:
        raise RuntimeError("This is a test error from scripts/test_observability.py")
    except RuntimeError:
        log.error("Observability check: webhook is working", exc_info=True)
    # Give the daemon thread a moment to POST before the process exits
    time.sleep(2)
    print("[webhook] Done — check #bot-logs in Discord for a red embed")

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
