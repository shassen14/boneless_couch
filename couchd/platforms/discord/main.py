# couchd/platforms/discord/main.py

import discord
import os
import logging
import sentry_sdk
from discord.ext import commands
from couchd.core.config import settings
from couchd.core.logger import setup_logging
from couchd.core.db import engine, Base

if settings.SENTRY_DSN:
    sentry_sdk.init(dsn=settings.SENTRY_DSN)

setup_logging(webhook_url=settings.BOT_LOGS_WEBHOOK_URL, bot_name="discord")

# Now we can grab a logger for this specific file
log = logging.getLogger(__name__)

# Start with the default, non-privileged intents
intents = discord.Intents.default()

# Explicitly enable the privileged members intent. This is crucial.
intents.members = True

# We will also need message content intent later for text commands, so let's enable it now.
intents.message_content = True

# Pass the configured intents to the bot.
bot = commands.Bot(command_prefix="/", intents=intents)


@bot.event
async def on_ready():
    """This event is triggered when the bot successfully connects to Discord."""
    log.info(f"Logged in as {bot.user} (ID: {bot.user.id})")


def load_cogs():
    log.info("Attempting to load cogs...")
    for filename in os.listdir("./couchd/platforms/discord/cogs"):
        if filename.endswith(".py") and filename != "__init__.py":
            try:
                cog_path = f"couchd.platforms.discord.cogs.{filename[:-3]}"
                bot.load_extension(cog_path)
                log.info(f"Successfully loaded cog: {cog_path}")
            except Exception as e:
                log.error(
                    f"Failed to load cog: {cog_path}", exc_info=e
                )  # Log any errors


if __name__ == "__main__":
    load_cogs()
    bot.run(settings.DISCORD_BOT_TOKEN)
