#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

echo "==> Pulling latest changes..."
git pull

echo "==> Rebuilding image..."
docker compose build

echo "==> Running migrations..."
docker compose run --rm discord alembic upgrade head

echo "==> Restarting bots..."
docker compose up -d --force-recreate

echo "==> Done. Logs:"
docker compose logs -f --tail=50
