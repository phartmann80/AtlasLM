#!/usr/bin/env bash
# Patch 016A - Step 3: restore the database + volumes onto the NEW server.
# Run ON THE NEW SERVER (85.215.225.0) as 'atlas', after the archive is copied here.
set -euo pipefail

ARCHIVE="${1:-}"
if [ -z "$ARCHIVE" ] || [ ! -f "$ARCHIVE" ]; then
  echo "Usage: $0 ~/atlas-migrate-YYYYMMDD-HHMMSS.tar.gz"
  exit 1
fi

APP_DIR="$HOME/atlaslm"
DB_CONTAINER="atlaslm-db-1"
DB_NAME="atlaslm"
DB_USER="atlas"
VOLUMES=("atlaslm_uploads" "atlaslm_audio")   # pgdata is restored via pg_restore, not tar

echo "[*] Unpacking archive"
WORK="$(mktemp -d)"
tar xzf "$ARCHIVE" -C "$WORK"
SRC="$(find "$WORK" -maxdepth 1 -type d -name 'atlas-migrate-*')"

echo "[*] Ensure stack is up (db must be running to restore into)"
cd "$APP_DIR"
docker compose up -d db
echo "    waiting for postgres to accept connections..."
for i in $(seq 1 30); do
  if docker exec "$DB_CONTAINER" pg_isready -U "$DB_USER" >/dev/null 2>&1; then break; fi
  sleep 2
done

echo "[*] Restoring database (drops and recreates objects)"
docker exec -i "$DB_CONTAINER" pg_restore -U "$DB_USER" -d "$DB_NAME" --clean --if-exists < "$SRC/db.dump"

echo "[*] Restoring file volumes"
for V in "${VOLUMES[@]}"; do
  if [ -f "$SRC/${V}.tar.gz" ]; then
    echo "    - $V"
    docker volume create "$V" >/dev/null
    docker run --rm -v "$V":/data -v "$SRC":/backup alpine \
      sh -c "rm -rf /data/* && tar xzf /backup/${V}.tar.gz -C /data"
  fi
done

rm -rf "$WORK"
echo "[OK] Restore complete. Next: run 04_dns_tls.sh to bring up the proxy + certs."
