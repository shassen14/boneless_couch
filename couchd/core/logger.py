# couchd/core/logger.py

import logging
import sys


def setup_logging(level=logging.INFO):
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

    # 4. Chief Engineer Trick: Silence noisy third-party libraries
    # Discord.py logs a LOT of background network pings. We only want to see warnings/errors from them.
    logging.getLogger("discord.gateway").setLevel(logging.WARNING)
    logging.getLogger("discord.http").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)

    root_logger.info("Centralized logging initialized. 🌿")
    return root_logger
