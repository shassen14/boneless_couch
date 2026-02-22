# couchd/platforms/discord/main.py

import discord
import os
import logging  # <-- ADD THIS
from discord.ext import commands
from couchd.core.config import settings

# --- SETUP LOGGING ---
# This will output logs to your console with a timestamp and log level.
handler = logging.StreamHandler()
formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
handler.setFormatter(formatter)

# Get the root logger and add our handler to it
logger = logging.getLogger()
logger.setLevel(logging.INFO)  # Set the lowest level of logs to show
logger.addHandler(handler)
# ---------------------

# Define the "Intents" for our bot.
# intents = discord.Intents.all()
# bot = commands.Bot(command_prefix="/", intents=intents)

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
    logger.info(f"Logged in as {bot.user} (ID: {bot.user.id})")
    logger.info("------")


def load_cogs():
    logger.info("Attempting to load cogs...")
    for filename in os.listdir("./couchd/platforms/discord/cogs"):
        if filename.endswith(".py") and filename != "__init__.py":
            try:
                cog_path = f"couchd.platforms.discord.cogs.{filename[:-3]}"
                bot.load_extension(cog_path)
                logger.info(f"Successfully loaded cog: {cog_path}")
            except Exception as e:
                logger.error(
                    f"Failed to load cog: {cog_path}", exc_info=e
                )  # Log any errors


if __name__ == "__main__":
    load_cogs()
    bot.run(settings.DISCORD_BOT_TOKEN)
