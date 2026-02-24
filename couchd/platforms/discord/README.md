# Discord Bot Setup Guide

This guide covers the repeatable process for creating and authenticating the Discord bot for the Content OS.

## 1. Create the Application

1. Go to the [Discord Developer Portal](https://discord.com/developers/applications).
2. Click **New Application** and name it (e.g., `BonelessCouch`).
3. Go to the **Bot** tab in the left menu.
4. Under **Token**, click **Reset Token**, copy it, and paste it into your `.env` file as `DISCORD_BOT_TOKEN`.

## 2. Enable Privileged Intents (CRITICAL)

For the bot to welcome users and read messages, it needs special permissions.

1. Still on the **Bot** tab, scroll down to **Privileged Gateway Intents**.
2. Turn **ON** the `SERVER MEMBERS INTENT`.
3. Turn **ON** the `MESSAGE CONTENT INTENT`.
4. Click **Save Changes**.

## 3. Disable Code Grant

1. Go to the **OAuth2 -> General** tab in the left menu.
2. Ensure **Requires OAuth2 Code Grant** is toggled **OFF**. (If this is on, the bot cannot be invited normally).
3. Save changes.

## 4. Generate the Invite Link

1. Go to **OAuth2 -> URL Generator**.
2. Under **SCOPES**, check _exactly_ these two boxes:
   - `bot`
   - `applications.commands` (Required for Slash Commands)
3. Under **BOT PERMISSIONS**, select `Administrator` (or explicitly select the permissions you want to grant).
4. Copy the Generated URL at the bottom of the page.

## 5. Invite the Bot

1. Paste the generated URL into your web browser.
2. Select your server and click **Authorize**.
3. If the bot is online (running via `uv run -m couchd.platforms.discord.main`), you can type `/sync` in your server to force Discord to load its slash commands.
