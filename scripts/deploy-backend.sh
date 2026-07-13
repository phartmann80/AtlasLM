#!/usr/bin/env bash
set -euo pipefail

# Versioned, repeatable backend release. Run as the non-root deploy user from
# the checked-out release source. Secrets are loaded only from the root-owned
# env file and never printed.

APP_ROOT="${APP_ROOT:-/opt/atlaslm}"
SOURCE_DIR="${SOURCE_DIR:-$(pwd)}"
RELEASE_ID="${RELEASE_ID:-$(git -C "$SOURCE_DIR" rev-parse --short HEAD)}"
RELEASE_DIR="$APP_ROOT/releases/$RELEASE_ID"
CURRENT_LINK="$APP_ROOT/current"
ENV_FILE="${ENV_FILE:-/etc/atlaslm/atlaslm.env}"
COMPOSE_FILE="$RELEASE_DIR/docker-compose.yaml"
SOURCE_COMPOSE_FILE="$SOURCE_DIR/docker-compose.yaml"
BACKUP_DIR="${BACKUP_DIR:-/var/backups/atlaslm}"

if [ "$(id -u)" -eq 0 ] && [ "${ALLOW_ROOT_DEPLOY:-0}" != "1" ]; then
  echo "Refusing to deploy as root. Use a non-root deploy user or set ALLOW_ROOT_DEPLOY=1 for an explicit emergency override." >&2
  exit 1
fi

test -r "$ENV_FILE"
test -f "$SOURCE_COMPOSE_FILE"
docker compose --env-file "$ENV_FILE" -f "$SOURCE_COMPOSE_FILE" config -q

mkdir -p "$RELEASE_DIR" "$BACKUP_DIR"
git -C "$SOURCE_DIR" archive --format=tar HEAD | tar -x -C "$RELEASE_DIR"

cd "$RELEASE_DIR"

docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" up -d db redis

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" exec -T db \
  pg_dump -U "${POSTGRES_USER:-atlaslm}" -d "${POSTGRES_DB:-atlaslm_db}" \
  | gzip > "$BACKUP_DIR/pre-${RELEASE_ID}-${STAMP}.sql.gz"

docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" exec -T db \
  psql -U "${POSTGRES_USER:-atlaslm}" -d "${POSTGRES_DB:-atlaslm_db}" \
  -v ON_ERROR_STOP=1 < migrations/010_ai_runtime_vertical_slice.sql

docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" build backend worker mastra
docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" up -d backend worker mastra

ln -sfn "$RELEASE_DIR" "$CURRENT_LINK.next"
mv -Tf "$CURRENT_LINK.next" "$CURRENT_LINK"

for attempt in $(seq 1 30); do
  if curl --fail --silent --show-error --max-time 5 https://api.atlaslm.cloud/health >/dev/null; then
    break
  fi
  sleep 2
done
curl --fail --silent --show-error https://api.atlaslm.cloud/health >/dev/null
docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" exec -T mastra wget -qO- http://127.0.0.1:8110/health >/dev/null
echo "AtlasLM backend release $RELEASE_ID is healthy."
