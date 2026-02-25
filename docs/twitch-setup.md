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

twitchio v3 handles OAuth via a built-in web server.

1. Run the bot: `python -m couchd.platforms.twitch.main`
2. Open a **private/incognito window**, log into Twitch as the **bot account**.
3. Visit `http://localhost:4343/oauth` and authorize.
4. The bot saves the token automatically. Subsequent runs load it without a browser step.

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

## 6. Chat Commands

| Command | Who | Description |
|---|---|---|
| `!commands` | Everyone | List available commands |
| `!lc` | Everyone | Show current LeetCode problem |
| `!project` | Everyone | Show current GitHub project |
| `!newvideo` | Everyone | Latest YouTube video title + link |
| `!lc <url>` | Mod/Broadcaster | Log a LeetCode solve |
| `!project <url>` | Mod/Broadcaster | Set active GitHub project |
| `!ad [mins]` | Mod/Broadcaster | Run an ad (e.g. `!ad 1.5` for 90s) |

Viewer commands are rate-limited (per-user and global cooldowns). Durations are in `CommandCooldowns` in `constants.py`.
