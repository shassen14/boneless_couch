"""Backfill ViewerInteraction rows from Twitch API historical data.

Usage:
    python -m scripts.backfill_viewer_interactions [--dry-run] [--force]
    python -m scripts.backfill_viewer_interactions --token <broadcaster_oauth_token> [--dry-run] [--force]

If --token is omitted, reads the broadcaster's token from .tio.tokens.json
(the file twitchio writes after OAuth — keyed by TWITCH_OWNER_ID).
"""

import argparse
import asyncio
import json
import logging
import pathlib
from datetime import datetime, timezone

from sqlalchemy import func, select

from couchd.core.config import settings
from couchd.core.constants import InteractionType
from couchd.core.clients.twitch import TwitchClient
from couchd.core.db import get_session
from couchd.core.models import ViewerInteraction

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

_TOKENS_FILE = pathlib.Path(__file__).resolve().parent.parent / ".tio.tokens.json"


async def _refresh_token(user_id: str) -> str:
    """Refreshes the stored token for user_id and writes it back to .tio.tokens.json."""
    import aiohttp
    if not _TOKENS_FILE.exists():
        raise FileNotFoundError(f"{_TOKENS_FILE} not found. Run the bot and complete OAuth first.")
    data = json.loads(_TOKENS_FILE.read_text())
    entry = data.get(user_id)
    if not entry:
        raise KeyError(f"No token for user_id={user_id} in {_TOKENS_FILE}.")

    async with aiohttp.ClientSession() as session:
        async with session.post("https://id.twitch.tv/oauth2/token", data={
            "grant_type": "refresh_token",
            "refresh_token": entry["refresh"],
            "client_id": settings.TWITCH_CLIENT_ID,
            "client_secret": settings.TWITCH_CLIENT_SECRET,
        }) as resp:
            if resp.status != 200:
                raise RuntimeError(f"Token refresh failed for {user_id} ({resp.status}): {await resp.text()}")
            refreshed = await resp.json()

    entry["token"] = refreshed["access_token"]
    entry["refresh"] = refreshed["refresh_token"]
    entry["last_validated"] = datetime.now(timezone.utc).isoformat()
    _TOKENS_FILE.write_text(json.dumps(data, indent=2))
    log.info("Token refreshed for user_id=%s.", user_id)
    return entry["token"]


async def _count_existing(interaction_type: InteractionType) -> int:
    async with get_session() as db:
        result = await db.execute(
            select(func.count()).where(ViewerInteraction.interaction_type == interaction_type)
        )
        return result.scalar_one()


async def backfill_followers(client: TwitchClient, token: str, *, dry_run: bool, force: bool) -> None:
    existing = await _count_existing(InteractionType.FOLLOW)
    if existing > 0 and not force:
        log.warning("Skipping followers backfill: %d rows already exist. Pass --force to override.", existing)
        return

    log.info("Backfilling followers...")
    total = 0
    cursor = None
    while True:
        items, cursor = await client.get_followers(settings.TWITCH_OWNER_ID, token, after=cursor)
        if not items:
            break
        if not dry_run:
            async with get_session() as db:
                for item in items:
                    followed_at_raw = item.get("followed_at", "")
                    try:
                        ts = datetime.fromisoformat(followed_at_raw.replace("Z", "+00:00"))
                    except (ValueError, AttributeError):
                        ts = datetime.now(timezone.utc)
                    db.add(ViewerInteraction(
                        interaction_type=InteractionType.FOLLOW,
                        username=item.get("user_login"),
                        display_name=item.get("user_name"),
                        timestamp=ts,
                    ))
        total += len(items)
        log.info("  ... %d followers processed", total)
        if not cursor:
            break
        await asyncio.sleep(0.1)
    log.info("Followers backfill complete: %d rows%s.", total, " (dry run)" if dry_run else "")


async def backfill_subscribers(client: TwitchClient, token: str, *, dry_run: bool, force: bool) -> None:
    existing = await _count_existing(InteractionType.SUB)
    if existing > 0 and not force:
        log.warning("Skipping subscribers backfill: %d rows already exist. Pass --force to override.", existing)
        return

    log.info("Backfilling subscribers...")
    total = 0
    cursor = None
    now = datetime.now(timezone.utc)
    while True:
        items, cursor = await client.get_subscribers(settings.TWITCH_OWNER_ID, token, after=cursor)
        if not items:
            break
        if not dry_run:
            async with get_session() as db:
                for item in items:
                    db.add(ViewerInteraction(
                        interaction_type=InteractionType.SUB,
                        username=item.get("user_login"),
                        display_name=item.get("user_name"),
                        tier=item.get("tier"),
                        timestamp=now,
                    ))
        total += len(items)
        log.info("  ... %d subscribers processed", total)
        if not cursor:
            break
        await asyncio.sleep(0.1)
    log.info("Subscribers backfill complete: %d rows%s.", total, " (dry run)" if dry_run else "")


async def backfill_bits(client: TwitchClient, token: str, *, dry_run: bool, force: bool) -> None:
    existing = await _count_existing(InteractionType.BITS)
    if existing > 0 and not force:
        log.warning("Skipping bits backfill: %d rows already exist. Pass --force to override.", existing)
        return

    log.info("Backfilling bits leaderboard...")
    items = await client.get_bits_leaderboard(settings.TWITCH_OWNER_ID, token, count=100)
    now = datetime.now(timezone.utc)
    if not dry_run and items:
        async with get_session() as db:
            for item in items:
                db.add(ViewerInteraction(
                    interaction_type=InteractionType.BITS,
                    username=item.get("user_login"),
                    display_name=item.get("user_name"),
                    bits=item.get("score"),
                    timestamp=now,
                ))
    log.info("Bits backfill complete: %d rows%s.", len(items), " (dry run)" if dry_run else "")


async def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill ViewerInteraction rows from Twitch API.")
    parser.add_argument("--token", default=None, help="Broadcaster OAuth user token. Defaults to .tio.tokens.json.")
    parser.add_argument("--dry-run", action="store_true", help="Fetch and log without writing to DB.")
    parser.add_argument("--force", action="store_true", help="Run even if rows already exist.")
    args = parser.parse_args()

    broadcaster_token = args.token or await _refresh_token(settings.TWITCH_OWNER_ID)
    bot_token = await _refresh_token(settings.TWITCH_BOT_ID)
    client = TwitchClient()
    # followers needs moderator:read:followers — lives on the bot token
    await backfill_followers(client, bot_token, dry_run=args.dry_run, force=args.force)
    await backfill_subscribers(client, broadcaster_token, dry_run=args.dry_run, force=args.force)
    await backfill_bits(client, broadcaster_token, dry_run=args.dry_run, force=args.force)
    log.info("Backfill finished.")


if __name__ == "__main__":
    asyncio.run(main())
