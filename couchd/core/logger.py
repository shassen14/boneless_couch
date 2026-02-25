# couchd/core/logger.py

import json
import logging
import sys
import threading
import traceback
import urllib.request


class DiscordWebhookHandler(logging.Handler):
    """
    Fires an HTTP POST to a Discord webhook on ERROR or CRITICAL log records.
    Runs in a daemon thread so it never blocks the event loop.
    """

    def __init__(self, webhook_url: str, bot_name: str):
        super().__init__(level=logging.ERROR)
        self.webhook_url = webhook_url
        self.bot_name = bot_name

    def emit(self, record: logging.LogRecord) -> None:
        threading.Thread(target=self._post, args=(record,), daemon=True).start()

    def _post(self, record: logging.LogRecord) -> None:
        try:
            msg = record.getMessage()
            tb = None
            if record.exc_info and record.exc_info[0] is not None:
                tb = "".join(traceback.format_exception(*record.exc_info))

            description = f"**{msg}**"
            if tb:
                max_tb = 3900 - len(description)
                if len(tb) > max_tb:
                    tb = "..." + tb[-max_tb:]
                description += f"\n```python\n{tb}\n```"

            color = 0xCC0000 if record.levelno >= logging.CRITICAL else 0xFF4500
            payload = {
                "embeds": [
                    {
                        "title": f"[{self.bot_name}] {record.levelname}: {record.name}"[:256],
                        "description": description[:4096],
                        "color": color,
                    }
                ]
            }
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                self.webhook_url,
                data=data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=5):
                pass
        except Exception:
            self.handleError(record)  # prints to stderr; visible in docker compose logs


def setup_logging(
    level=logging.INFO,
    webhook_url: str | None = None,
    bot_name: str = "bot",
):
    """
    Sets up the central logging configuration for the entire monorepo.
    Call this ONCE at the start of your main application scripts (e.g., main.py).
    """
    # 1. Create a standardized, highly readable format
    # Example: 2026-02-22 12:49:55 | INFO     | couchd.platforms.discord.cogs.welcome | User joined!
    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # 2. Set up the Console Handler (prints to terminal)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)

    # 3. Configure the Root Logger
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # This prevents duplicate logs if setup_logging is accidentally called twice
    if not root_logger.handlers:
        root_logger.addHandler(console_handler)

    # 4. Attach Discord webhook handler for ERROR/CRITICAL if configured
    if webhook_url:
        root_logger.addHandler(DiscordWebhookHandler(webhook_url, bot_name))

    # 5. Silence noisy third-party libraries
    logging.getLogger("discord.gateway").setLevel(logging.WARNING)
    logging.getLogger("discord.http").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)

    root_logger.info("Centralized logging initialized.")
    return root_logger
