# Twitch Bot Setup Guide

This guide covers how to set up the Twitch bot.

**Recommendation:** It is highly recommended to create a separate, secondary Twitch account (e.g., `BonelessCouchBot`) to act as the bot. This looks more professional in chat than your main streamer account replying to itself.

## 1. Register the Developer Application

_Note: You can do this step on either your main or bot account._

1. Go to the [Twitch Developer Console](https://dev.twitch.tv/console).
2. Click **Register Your Application**.
   - **Name:** Your bot's name.
   - **OAuth Redirect URLs:** `http://localhost:4343/oauth` (twitchio v3 default).
   - **Category:** `Chat Bot`
3. Click **Manage** on your new app.
4. Copy the **Client ID** and generate a **Client Secret**.
5. Paste both into your `.env` file as `TWITCH_CLIENT_ID` and `TWITCH_CLIENT_SECRET`.

## 2. Authorize the Bot (First Run)

twitchio v3 handles the OAuth flow automatically via a built-in web server.

1. Fill in `.env` with `TWITCH_CLIENT_ID`, `TWITCH_CLIENT_SECRET`, `TWITCH_BOT_ID`, `TWITCH_OWNER_ID`, and `TWITCH_CHANNEL`.
2. Run the bot: `python -m couchd.platforms.twitch.main`
3. Open a **Private/Incognito window** and log into Twitch as the **bot account**.
4. Visit `http://localhost:4343/oauth` in that window.
5. Authorize the app. The bot will save the token automatically and subscribe to chat.

On subsequent runs the saved token is loaded automatically — no browser step needed.

## 3. Get the Bot User ID

TwitchIO v3 requires the numeric ID of your bot account.

1. Ensure your `.env` has `TWITCH_BOT_TOKEN` and `TWITCH_CLIENT_ID` filled out.
2. In your terminal, run our utility script:
   ```bash
   uv run python scripts/get_twitch_bot_id.py
   ```
3. Copy the outputted "Bot ID" into your `.env` file as `TWITCH_BOT_ID`.

## 4. Grant Channel Permissions

For the bot to run ads or manage chat, it needs privileges in your main stream channel.

1. Go to your **main stream channel's chat** (logged in as the streamer).
2. Type `/mod [YourBotAccountName]` and hit enter.
3. Add your main channel name to the `.env` file as `TWITCH_CHANNEL`.
