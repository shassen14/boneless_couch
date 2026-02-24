# scripts/get_twitch_bot_id.py
import asyncio
import twitchio
from couchd.core.config import settings

# --- EDIT THIS LINE ---
# Since we are fetching IDs, we need to know WHO to look for.
# Type your bot's Twitch username here.
BOT_USERNAME = "lildoufu"
# ----------------------


async def main() -> None:
    # We use the Client ID and Secret from your .env via settings
    client = twitchio.Client(
        client_id=settings.TWITCH_CLIENT_ID, client_secret=settings.TWITCH_CLIENT_SECRET
    )

    print(f"Connecting to Twitch API...")

    async with client:
        # Client Credentials Flow (App Access Token)
        await client.login()

        # We fetch both the Streamer (Owner) and the Bot
        target_logins = [settings.TWITCH_CHANNEL, BOT_USERNAME]

        print(f"Fetching IDs for: {target_logins}...")
        users = await client.fetch_users(logins=target_logins)

        print("\n✅ SUCCESS!")
        print("-" * 40)

        found_bot = False
        found_owner = False

        for u in users:
            print(f"User: {u.name:<20} | ID: {u.id}")

            if u.name.lower() == settings.TWITCH_CHANNEL.lower():
                print(f'-> Add to .env: TWITCH_OWNER_ID="{u.id}"')
                found_owner = True
            elif u.name.lower() == BOT_USERNAME.lower():
                print(f'-> Add to .env: TWITCH_BOT_ID="{u.id}"')
                found_bot = True

        print("-" * 40)

        if not found_bot:
            print(f"⚠️ Could not find user '{BOT_USERNAME}'. Check spelling.")
        if not found_owner:
            print(f"⚠️ Could not find user '{settings.TWITCH_CHANNEL}'. Check .env.")


if __name__ == "__main__":
    asyncio.run(main())
