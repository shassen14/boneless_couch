# Running on Raspberry Pi (Production)

Both bots run as Docker containers built from source on the Pi. This is the intended 100% runtime environment.

## Prerequisites

- Docker and Docker Compose installed on the Pi
- A running PostgreSQL instance (external — not included in compose)
- The repo cloned on the Pi

## Setup

**1. Create your `.env` file**

```bash
cp .env.example .env
```

Fill in all required values. See `.env.example` for the full list. The database host should be reachable from the Pi.

**2. Build the image**

```bash
docker build -t boneless-couch .
```

**3. Run migrations** (first time, or after pulling changes that add migrations)

```bash
docker compose run --rm discord alembic upgrade head
```

**4. Start the bots**

```bash
docker compose up -d
```

Both services restart automatically unless explicitly stopped.

## Twitch OAuth (first run only)

The Twitch bot requires an OAuth token on first run. After starting, visit:

```
http://<pi-ip>:4343/oauth
```

Then restart the twitch service:

```bash
docker compose restart twitch
```

## Common commands

```bash
# View logs
docker compose logs -f

# Logs for one service
docker compose logs -f discord
docker compose logs -f twitch

# Restart a service
docker compose restart discord

# Stop everything
docker compose down

# Rebuild after a code change
docker build -t boneless-couch . && docker compose up -d
```

## How it works

`config.py` loads secrets from a `.env` file whose path is read from `.env.path`. The `Dockerfile` bakes `/app/.env` into `.env.path`, and `docker-compose.yml` mounts your local `.env` there. You never need to create `.env.path` on the Pi.
