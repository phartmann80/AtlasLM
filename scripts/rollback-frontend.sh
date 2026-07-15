#!/usr/bin/env bash
set -euo pipefail

APP_ROOT="${APP_ROOT:-/opt/atlaslm}"
TARGET_RELEASE="${1:?Usage: rollback-frontend.sh <release-id>}"
RELEASE_DIR="$APP_ROOT/frontend-releases/$TARGET_RELEASE"
CURRENT_LINK="${CURRENT_LINK:-$APP_ROOT/frontend-current}"
ENV_FILE="${ENV_FILE:-/etc/atlaslm/atlaslm.env}"
COMPOSE_FILE="$RELEASE_DIR/docker-compose.frontend.yml"
FRONTEND_PORT="${ATLAS_FRONTEND_PORT:-3010}"
IMAGE="atlaslm-frontend:$TARGET_RELEASE"

if [ "$(id -u)" -eq 0 ] && [ "${ALLOW_ROOT_DEPLOY:-0}" != "1" ]; then
  echo "Refusing to roll back as root. Use atlasdeploy or set ALLOW_ROOT_DEPLOY=1 for an explicit emergency override." >&2
  exit 1
fi

test -d "$RELEASE_DIR"
test -r "$ENV_FILE"
test -f "$COMPOSE_FILE"
docker image inspect "$IMAGE" >/dev/null

cd "$RELEASE_DIR"

export ATLAS_FRONTEND_IMAGE="$IMAGE"
export ATLAS_FRONTEND_PORT="$FRONTEND_PORT"

docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" config -q
docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" up -d --no-deps frontend

for attempt in $(seq 1 60); do
  if curl --fail --silent --show-error --max-time 5 "http://127.0.0.1:$FRONTEND_PORT/login" >/dev/null; then
    break
  fi
  sleep 2
done

curl --fail --silent --show-error --max-time 10 "http://127.0.0.1:$FRONTEND_PORT/login" >/dev/null
ln -sfn "$RELEASE_DIR" "$CURRENT_LINK.next"
mv -Tf "$CURRENT_LINK.next" "$CURRENT_LINK"

echo "AtlasLM frontend rolled back to $TARGET_RELEASE."
