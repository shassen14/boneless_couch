# YouTube Live Chat Commands

Commands are prefixed with `!` and work in YouTube live chat during an active stream.

## Viewer Commands

| Command        | Description                                              |
| -------------- | -------------------------------------------------------- |
| `!commands`    | Link to this page                                        |
| `!lc`          | Show the current LeetCode problem URL                    |
| `!project`     | Show the current GitHub project being worked on          |
| `!game`        | Show the current game being played                       |
| `!edit`        | Show the current video editing subject                   |
| `!topic`       | Show the current just chatting topic                     |
| `!task`        | Show the current active micro-task                       |
| `!status`      | Show current activity and active task in one reply       |
| `!idea <text>` | Submit a community idea to be voted on in Discord        |
| `!newvideo`    | Show the latest YouTube upload                           |
| `!socials`     | Show all social links (Twitch, YouTube, GitHub, Discord) |
| `!discord`     | Show the Discord invite link                             |

## Mod / Broadcaster Commands

| Command                     | Description                                                     |
| --------------------------- | --------------------------------------------------------------- |
| `!lc <url>`                 | Log a new LeetCode problem (LeetCode problem or submission URL) |
| `!project <url>`            | Set the active GitHub project (GitHub repo URL)                 |
| `!game <name>`              | Log the current game being played                               |
| `!edit <subject>`           | Log the current video editing subject                           |
| `!topic <subject>`          | Log the current just chatting topic                             |
| `!task <detail>`            | Set the active micro-task                                       |
| `!task done`                | Clear the active micro-task                                     |
| `!delete <message_id>`      | Delete a specific chat message by its YouTube message ID        |
| `!timeout <channel_id> <s>` | Temporarily ban a viewer for `<s>` seconds                      |
| `!ban <channel_id>`         | Permanently ban a viewer from the live chat                     |
| `!unban <ban_id>`           | Remove a ban using the YouTube ban ID                           |

> **Note:** YouTube does not expose display names in ban/timeout commands — you need the viewer's YouTube channel ID, which appears in the chat message metadata.

## Chat Timers

The bot automatically sends rotating promo messages every `CHAT_TIMER_INTERVAL_MINUTES` (default 20 min) while a live chat is active.

| Message (when configured)  | Social link used |
| -------------------------- | ---------------- |
| Discord community invite   | `SOCIAL_DISCORD` |
| Twitch follow reminder     | `SOCIAL_TWITCH`  |
| GitHub projects link       | `SOCIAL_GITHUB`  |
| YouTube subscribe reminder | `SOCIAL_YOUTUBE` |

## Differences from Twitch

| Feature                 | Twitch           | YouTube                          |
| ----------------------- | ---------------- | -------------------------------- |
| `!lurk` / `!unlurk`     | Yes              | No                               |
| `!socials` / `!discord` | Yes              | Yes                              |
| `!clip`                 | Yes              | No                               |
| `!ad`                   | Yes              | No                               |
| `!alerts`               | Yes              | No                               |
| Mod ban/timeout         | Via Twitch UI    | `!ban`, `!timeout`               |
| Auto shoutout on raid   | Yes (5+ viewers) | No (YouTube has no raid feature) |
| Auto follow/sub welcome | Yes              | No                               |
