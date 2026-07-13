#!/usr/bin/env bash
set -euo pipefail

APP_ROOT="${APP_ROOT:-/opt/atlaslm}"
TARGET_RELEASE="${1:?Usage: rollback-backend.sh <release-id>}"
ENV_FILE="${ENV_FILE:-/etc/atlaslm/atlaslm.env}"
RELEASE_DIR="$APP_ROOT/releases/$TARGET_RELEASE"

if [ "$(id -u)" -eq 0 ] && [ "${ALLOW_ROOT_DEPLOY:-0}" != "1" ]; then
  echo "Refusing to roll back as root. Use a non-root deploy user or set ALLOW_ROOT_DEPLOY=1 for an explicit emergency override." >&2
  exit 1
fi

test -d "$RELEASE_DIR"
test -r "$ENV_FILE"
docker compose --env-file "$ENV_FILE" -f "$RELEASE_DIR/docker-compose.yaml" config -q
ln -sfn "$RELEASE_DIR" "$APP_ROOT/current.next"
mv -Tf "$APP_ROOT/current.next" "$APP_ROOT/current"
docker compose --env-file "$ENV_FILE" -f "$RELEASE_DIR/docker-compose.yaml" up -d backend worker mastra
curl --fail --silent --show-error --max-time 10 https://api.atlaslm.cloud/health >/dev/null
echo "AtlasLM backend rolled back to $TARGET_RELEASE."
