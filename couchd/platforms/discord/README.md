# Discord Bot Setup

## 1. Create the Application

1. Go to the [Discord Developer Portal](https://discord.com/developers/applications).
2. Click **New Application** and name it (e.g. `BonelessCouch`).
3. Go to the **Bot** tab → **Reset Token**, copy it → paste into `.env` as `DISCORD_BOT_TOKEN`.

## 2. Enable Privileged Intents

1. On the **Bot** tab, scroll to **Privileged Gateway Intents**.
2. Enable **Server Members Intent** and **Message Content Intent**.
3. Save changes.

## 3. Generate the Invite Link

1. Go to **OAuth2 → URL Generator**.
2. Under **Scopes**, select `bot` and `applications.commands`.
3. Under **Bot Permissions**, select `Administrator` (or at minimum: Send Messages, Embed Links,
   Create Public Threads, Manage Messages, Read Message History, View Channels).
4. Copy the generated URL, paste it in a browser, select your server, and authorize.

## 4. Configure Channels (in Discord)

Once the bot is running, use slash commands as a server admin:

```
/setup stream_updates_channel  #channel   — go-live announcements and stream recaps
/setup video_updates_channel   #channel   — YouTube upload embeds + discussion threads
/setup video_updates_role      @role      — role pinged on new YouTube uploads (optional)
/setup welcome_channel         #channel   — member join messages
/setup role_channel            #channel   — role selection channel
```

## 5. Run

```bash
python -m couchd.platforms.discord.main
```

> **Note:** The bot requires the **Create Public Threads** permission in any channel configured
> for video updates, so discussion threads can be opened automatically on new uploads.
