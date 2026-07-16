#!/usr/bin/env bash
# Patch 016A - Step 4: bring up the app + Caddy TLS proxy on the NEW server.
# Run ON THE NEW SERVER (85.215.225.0) as 'atlas', from the app directory.
# DNS for atlaslm.cloud already points here, so Caddy can issue certs immediately.
set -euo pipefail

APP_DIR="$HOME/atlaslm"
cd "$APP_DIR"

echo "[*] Checking DNS resolves to this server"
RESOLVED="$(getent hosts atlaslm.cloud | awk '{print $1}' | head -1 || true)"
echo "    atlaslm.cloud -> ${RESOLVED:-unresolved}"
if [ "$RESOLVED" != "85.215.225.0" ]; then
  echo "    WARNING: DNS does not point to 85.215.225.0 yet. Caddy cert issuance may fail."
  echo "    Continue only if you know propagation is in flight."
fi

echo "[*] Bringing up full stack with TLS overlay"
docker compose -f docker-compose.yaml -f config/docker-compose.prod.yaml up -d --build

echo "[*] Waiting for Caddy to obtain certificate (Let's Encrypt)"
sleep 15
docker compose logs --tail=40 caddy || true

echo "[OK] Stack up. Verify with 05_smoke_test.sh"
