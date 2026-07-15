#!/usr/bin/env bash
set -euo pipefail

# Deploy one immutable AtlasLM frontend release. The release source must already
# exist under /opt/atlaslm/frontend-releases. Secrets remain in the protected
# server env file; only the public Supabase URL and anonymous browser key are
# supplied to the Next.js build.

APP_ROOT="${APP_ROOT:-/opt/atlaslm}"
RELEASE_ID="${RELEASE_ID:?Set RELEASE_ID to the immutable frontend release identifier}"
RELEASE_DIR="${RELEASE_DIR:-$APP_ROOT/frontend-releases/$RELEASE_ID}"
CURRENT_LINK="${CURRENT_LINK:-$APP_ROOT/frontend-current}"
ENV_FILE="${ENV_FILE:-/etc/atlaslm/atlaslm.env}"
COMPOSE_FILE="$RELEASE_DIR/docker-compose.frontend.yml"
FRONTEND_PORT="${ATLAS_FRONTEND_PORT:-3010}"
IMAGE="atlaslm-frontend:$RELEASE_ID"

if [ "$(id -u)" -eq 0 ] && [ "${ALLOW_ROOT_DEPLOY:-0}" != "1" ]; then
  echo "Refusing to deploy as root. Use atlasdeploy or set ALLOW_ROOT_DEPLOY=1 for an explicit emergency override." >&2
  exit 1
fi

test -d "$RELEASE_DIR"
test -r "$ENV_FILE"
test -f "$COMPOSE_FILE"
test -f "$RELEASE_DIR/frontend/Dockerfile"

cd "$RELEASE_DIR"

export ATLAS_FRONTEND_IMAGE="$IMAGE"
export ATLAS_FRONTEND_PORT="$FRONTEND_PORT"

docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" config -q
docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" build --pull frontend

if docker history --no-trunc "$IMAGE" | grep -Eq 'SUPABASE_SERVICE_ROLE_KEY|ATLAS_INTERNAL_SIGNING_SECRET|GATEWAY_API_MASTRA_KEY'; then
  echo "Refusing release: privileged server variable name found in frontend image history." >&2
  exit 1
fi

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

IMAGE_ID="$(docker image inspect --format '{{.Id}}' "$IMAGE")"
CONTAINER_ID="$(docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" ps -q frontend)"

echo "AtlasLM frontend release $RELEASE_ID is healthy on loopback port $FRONTEND_PORT."
echo "Frontend image ID: $IMAGE_ID"
echo "Frontend container ID: $CONTAINER_ID"
