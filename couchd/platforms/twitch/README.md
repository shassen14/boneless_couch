# Twitch Bot Setup Guide

This guide covers how to set up the Twitch bot.

**Recommendation:** It is highly recommended to create a separate, secondary Twitch account (e.g., `BonelessCouchBot`) to act as the bot. This looks more professional in chat than your main streamer account replying to itself.

## 1. Register the Developer Application

_Note: You can do this step on either your main or bot account._

1. Go to the [Twitch Developer Console](https://dev.twitch.tv/console).
2. Click **Register Your Application**.
   - **Name:** Your bot's name.
   - **OAuth Redirect URLs:** `http://localhost:3000` (Required for our token generation step).
   - **Category:** `Chat Bot`
3. Click **Manage** on your new app.
4. Copy the **Client ID** and generate a **Client Secret**.
5. Paste both into your `.env` file as `TWITCH_CLIENT_ID` and `TWITCH_CLIENT_SECRET`.

## 2. Generate the User Access Token (The "Key")

We must generate a token that links your Developer App to your Bot Account.

1. Open a **Private/Incognito window** in your browser.
2. Log into Twitch using the **account you want the bot to type as** (e.g., your secondary bot account).
3. Construct this exact URL, replacing `YOUR_CLIENT_ID_HERE` with your actual Client ID from step 1:
   ```text
   https://id.twitch.tv/oauth2/authorize?client_id=YOUR_CLIENT_ID_HERE&redirect_uri=http://localhost:3000&response_type=token&scope=chat:read+chat:edit+channel:manage:broadcast+channel:edit:commercial
   ```
4. Paste that URL into your incognito browser and hit Enter.
5. Click **Authorize**.
6. You will be redirected to a broken `localhost` page. **This is normal.**
7. Look at the URL bar. Copy the text _after_ `access_token=` and _before_ `&scope=`.
8. Paste this into your `.env` file as `TWITCH_BOT_TOKEN="oauth:your_copied_token"`.

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
