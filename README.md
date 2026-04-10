# BonelessCouch

A self-hosted bot system that ties together Twitch, Discord, YouTube, and LeetCode for a programming streamer. When you go live, Discord gets notified. When you log a LeetCode problem in Twitch chat, a Discord forum thread appears automatically. When you upload a YouTube video, your community is pinged. All stream activity is timestamped and stored so you can reference it later.

Built for a single streamer's community — not a generic multi-tenant bot.

---

## What it does

**Discord bot**
- Posts a go-live embed when the stream starts; edits it offline with a recap (duration, peak viewers, problems solved, projects worked on)
- Announces new YouTube uploads with a thumbnail embed and opens a discussion thread
- Creates a forum thread per LeetCode problem with difficulty, contest rating, and viewer solution links
- Welcomes new members, surfaces social links, and serves slash commands for community info

**Twitch bot**
- Logs LeetCode problems (`!lc <url>`), project switches (`!project <url>`), and activity (`!game`, `!edit`, `!topic`, `!task`) with VOD timestamps
- Viewers can look up the current problem (`!lc`), project (`!project`), latest video (`!newvideo`), or status (`!status`)
- Any viewer pasting a LeetCode submission URL in chat is logged automatically
- Auto-clips (`!clip`) and community idea collection (`!idea`)
- Manages ad budget and auto-fires ads if the hourly target isn't met

---

## Requirements

- Python 3.13+
- PostgreSQL
- [`uv`](https://github.com/astral-sh/uv) (package manager)
- A Discord bot token (from Discord Developer Portal)
- A Twitch application + bot account (from Twitch Developer Console)
- A YouTube channel ID (optional)

---

## Installation

```bash
git clone https://github.com/shassen14/boneless_couch
cd boneless_couch

uv sync                  # install all dependencies into a managed venv
cp .env.example .env     # fill in credentials (see Configuration below)
alembic upgrade head     # create all database tables
```

---

## Configuration

Edit `.env` with your credentials:

```env
# Discord
DISCORD_BOT_TOKEN=""

# Twitch application (https://dev.twitch.tv/console)
TWITCH_CLIENT_ID=""
TWITCH_CLIENT_SECRET=""

# Twitch bot account
TWITCH_BOT_TOKEN=""
TWITCH_BOT_ID=""

# The streamer's channel to watch
TWITCH_OWNER_ID=""
TWITCH_CHANNEL="yourchannel"

# Ad budget target (minutes of ads per hour)
TWITCH_AD_MINUTES_PER_HOUR=3

# YouTube (optional — omit to disable video announcements and !newvideo)
YOUTUBE_CHANNEL_ID=""

# LeetCode (optional — enables auto-detection of streamer's own AC submissions)
LEETCODE_USERNAME=""

# Social links shown by /socials and !socials
SOCIAL_TWITCH="https://twitch.tv/yourchannel"
SOCIAL_YOUTUBE="https://youtube.com/@yourchannel"
SOCIAL_GITHUB="https://github.com/yourprofile"

# PostgreSQL
DB_USER=""
DB_PASSWORD=""
DB_HOST=""
DB_PORT=5432
DB_NAME=""

# Optional observability
SENTRY_DSN=""
BOT_LOGS_WEBHOOK_URL=""
```

---

## Running

Open two terminals (or use a process manager):

```bash
# Terminal 1 — Discord bot
python -m couchd.platforms.discord.main

# Terminal 2 — Twitch bot (first run only: complete the OAuth flow)
python -m couchd.platforms.twitch.main
# Visit: http://localhost:4343/oauth?scopes=user:read:chat+user:write:chat+user:bot+clips:edit+user:manage:whispers+moderator:manage:banned_users+moderator:manage:chat_messages+moderator:manage:announcements
```

After completing OAuth once, the token is cached and future starts don't require browser interaction.

---

## Discord Server Setup

After inviting the bot, configure channels and roles with slash commands:

```
/setup stream_updates_channel   — where go-live embeds are posted
/setup video_updates_channel    — where YouTube upload embeds are posted
/setup video_updates_role       — role pinged on new uploads
/setup problems_forum           — forum channel for LeetCode threads
/setup welcome_channel          — where new member messages appear
```

Run `/dbtest` to verify the database connection is working.

---

## Usage

### Streamer workflows

**Starting a LeetCode session on stream:**
```
!lc https://leetcode.com/problems/two-sum/
→ ✅ 1. Two Sum | Easy | Rating: 1163 @ 0:23:47
```
A Discord forum thread is automatically created (or updated if the problem was done before) with the difficulty and rating. Viewers can paste their submission links in chat — each gets logged as a separate reply in the thread.

**Switching projects:**
```
!project https://github.com/you/your-repo
→ ✅ Project: your-repo — Brief description from GitHub
```

**Logging other activity:**
```
!game Hollow Knight        → logs a gaming session
!edit "thumbnail design"   → logs video editing
!topic system design       → logs a discussion topic
!task implement BFS        → sets a micro-task visible via !status
!task done                 → clears the task
```

**Creating a clip:**
```
!clip clutch submission    → creates a 30s Twitch clip, logs it with VOD timestamp
```

**Collecting community ideas:**
```
!idea add a Codeforces rating command
→ 💡 Idea noted! The community can vote on it in Discord.
```

### Viewer commands

| Command | Description |
|---|---|
| `!lc` | Current LeetCode problem URL |
| `!project` | Current GitHub project |
| `!newvideo` | Latest YouTube video |
| `!status` | Current activity and task |
| `!commands` | Full command list |
| `!clip [title]` | Clip this moment |
| `!idea <text>` | Submit a community idea |

### Discord slash commands

| Command | Description |
|---|---|
| `/lc` | Most recent LC problem from last stream |
| `/project` | Most recent project from last stream |
| `/latest` | Latest YouTube upload |
| `/socials` | All platform links |

---

## Development

```bash
uv sync --group dev      # includes pytest, pytest-asyncio, aiosqlite
pytest
```

New Alembic migration:
```bash
alembic revision --autogenerate -m "describe the change"
alembic upgrade head
```
