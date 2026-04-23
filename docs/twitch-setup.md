# Twitch Bot Setup

**Recommendation:** Use a separate bot account (e.g. `BonelessCouchBot`) rather than your
main streamer account — it looks more professional in chat.

## 1. Register the Developer Application

1. Go to the [Twitch Developer Console](https://dev.twitch.tv/console).
2. Click **Register Your Application**:
   - **Name:** Your bot's name
   - **OAuth Redirect URL:** `http://localhost:4343/oauth`
   - **Category:** Chat Bot
3. Copy the **Client ID** and generate a **Client Secret** → paste into `.env` as
   `TWITCH_CLIENT_ID` and `TWITCH_CLIENT_SECRET`.

## 2. Get the Bot User ID

1. Fill in `TWITCH_BOT_TOKEN` and `TWITCH_CLIENT_ID` in `.env`.
2. Run the utility script:
   ```bash
   uv run python scripts/get_twitch_bot_id.py
   ```
3. Copy the outputted ID → paste into `.env` as `TWITCH_BOT_ID`.

## 3. Authorize the Bot (First Run)

twitchio v3 handles OAuth via a built-in web server. Two accounts must authorize: the bot account and your streamer account.

### 3a. Authorize the bot account

1. Run the bot: `python -m couchd.platforms.twitch.main`
2. Open a **private/incognito window**, log into Twitch as the **bot account**.
3. Visit the following URL and authorize:
   ```
   http://localhost:4343/oauth?scopes=user:read:chat+user:write:chat+user:bot+channel:bot+moderator:manage:chat_messages+moderator:manage:banned_users+moderator:manage:announcements+moderator:manage:chat_settings+moderator:manage:shoutouts+moderator:manage:automod+user:manage:whispers+moderation:read+moderator:read:followers+moderator:read:chatters
   ```

### 3b. Authorize the streamer account

Subscriptions for subs, bits, raids, redemptions, and stream online/offline require the **broadcaster's** user token.

4. In the **same (or a new) incognito window**, log into Twitch as your **streamer account**.
5. Visit the following URL and authorize:
   ```
   http://localhost:4343/oauth?scopes=channel:read:subscriptions+bits:read+channel:read:redemptions+channel:manage:redemptions+channel:manage:broadcast+channel:manage:raids+channel:edit:commercial+channel:manage:ads+channel:read:ads+clips:edit+channel:read:polls+channel:read:predictions+channel:read:goals+channel:read:hype_train+channel:read:vips+user:read:emotes
   ```
6. The bot saves both tokens automatically. Subsequent runs load them without a browser step.

> **Re-authorizing after adding scopes:** Append `&force_verify=true` to the OAuth URL and
> repeat the relevant step above. Without it, Twitch silently returns the old cached token and
> the new scopes are not granted. twitchio will overwrite the stored token automatically.

## 4. Grant Channel Permissions

In your main stream channel's chat (logged in as the streamer):

```
/mod YourBotAccountName
```

This allows the bot to run ads and manage chat.

## 5. Configure `.env`

```
TWITCH_CLIENT_ID=""
TWITCH_CLIENT_SECRET=""
TWITCH_BOT_TOKEN=""
TWITCH_BOT_ID=""
TWITCH_OWNER_ID=""       # numeric ID of your streamer account
TWITCH_CHANNEL=""        # your channel name (lowercase)
TWITCH_AD_MINUTES_PER_HOUR=3

# Optional — enables !newvideo command and post-ad video messages
YOUTUBE_CHANNEL_ID=""
```
