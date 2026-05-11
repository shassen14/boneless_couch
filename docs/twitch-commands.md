# Twitch Chat Commands

## Viewer Commands

| Command         | Description                                              |
| --------------- | -------------------------------------------------------- |
| `!commands`     | Link to this page                                        |
| `!lc`           | Show the current LeetCode problem URL                    |
| `!project`      | Show the current GitHub project being worked on          |
| `!game`         | Show the current game being played                       |
| `!edit`         | Show the current video editing subject                   |
| `!topic`        | Show the current just chatting topic                     |
| `!task`         | Show the current active micro-task                       |
| `!status`       | Show current activity and active task in one reply       |
| `!clip [title]` | Create a Twitch clip of this moment                      |
| `!idea <text>`  | Submit a community idea to be voted on in Discord        |
| `!newvideo`     | Show the latest YouTube upload                           |
| `!lurk`         | Let chat know you're lurking                             |
| `!unlurk`       | Announce your return from lurk                           |
| `!socials`      | Show all social links (Twitch, YouTube, GitHub, Discord) |
| `!discord`      | Show the Discord invite link                             |

## Mod / Broadcaster Commands

| Command             | Description                                                                                     |
| ------------------- | ----------------------------------------------------------------------------------------------- |
| `!lc <url>`         | Log a new LeetCode problem (LeetCode problem or submission URL)                                 |
| `!project <url>`    | Set the active GitHub project (GitHub repo URL)                                                 |
| `!game <name>`      | Log the current game being played                                                               |
| `!edit <subject>`   | Log the current video editing subject                                                           |
| `!topic <subject>`  | Log the current just chatting topic                                                             |
| `!task <detail>`    | Set the active micro-task                                                                       |
| `!task done`        | Clear the active micro-task                                                                     |
| `!ad [mins]`        | Run an ad — optional duration in minutes (e.g. `!ad 1.5` for 90s), defaults to remaining budget |
| `!alerts on`        | Re-enable the alert overlay after it was turned off                                             |
| `!alerts off`       | Disable alerts immediately — stops audio and clears any visible card                            |
| `!alerts audio on`  | Re-enable alert audio (visuals continue playing regardless)                                     |
| `!alerts audio off` | Mute alert audio — overlay animations still play, no sound                                      |
| `!alerts clear`     | Flush the alert queue and stop current audio without disabling future alerts                    |

## Chat Timers

The bot automatically sends rotating promo messages every `CHAT_TIMER_INTERVAL_MINUTES` (default 20 min) during an active stream. Messages are only sent when the stream is live.

| Message (when configured) | Social link used |
| ------------------------- | ---------------- |
| Discord community invite  | `SOCIAL_DISCORD` |
| YouTube channel link      | `SOCIAL_YOUTUBE` |
| GitHub projects link      | `SOCIAL_GITHUB`  |
| Twitch follow reminder    | `SOCIAL_TWITCH`  |

Messages rotate in order so each gets equal airtime over a long stream.

## Automatic Bot Behaviors

These fire without any command — the bot responds to Twitch events automatically.

| Event             | Bot Response                                                                 |
| ----------------- | ---------------------------------------------------------------------------- |
| New follower      | Welcome message in chat (during active stream only)                          |
| New subscriber    | Welcome message in chat                                                      |
| Resub             | Acknowledgement with cumulative month count                                  |
| Gift sub bomb     | Thank-you message naming the gifter and count                                |
| Bits cheer        | Thank-you message with bit count                                             |
| Raid (any size)   | Welcome message to raider and their viewers                                  |
| Raid (5+ viewers) | Twitch shoutout sent automatically in addition to the welcome message        |
| Ad break start    | Warning message 60s before auto-ads; return-time announcement when it starts |
| Ad break end      | "We're back" message                                                         |
