#!/usr/bin/env bash
# Patch 016A - Step 2: dump the live database + volumes from the OLD server.
# Run ON THE OLD SERVER (217.154.11.234) as the user that owns the stack.
# Produces a single timestamped archive you copy to the new server.
set -euo pipefail

# --- adjust if your old stack differs ---
OLD_DB_CONTAINER="atlaslm-db-1"          # postgres container name on old box
DB_NAME="atlaslm"
DB_USER="atlas"
APP_DIR="$HOME/atlaslm"                   # where docker-compose.yaml lives on old box
# named volumes to capture (uploads, generated audio, etc.)
VOLUMES=("atlaslm_uploads" "atlaslm_audio" "atlaslm_pgdata")

STAMP="$(date +%Y%m%d-%H%M%S)"
OUT="$HOME/atlas-migrate-$STAMP"
mkdir -p "$OUT"

echo "[*] Dumping Postgres database '$DB_NAME'"
docker exec "$OLD_DB_CONTAINER" pg_dump -U "$DB_USER" -Fc "$DB_NAME" > "$OUT/db.dump"

echo "[*] Snapshotting named volumes"
for V in "${VOLUMES[@]}"; do
  if docker volume inspect "$V" >/dev/null 2>&1; then
    echo "    - $V"
    docker run --rm -v "$V":/data -v "$OUT":/backup alpine \
      tar czf "/backup/${V}.tar.gz" -C /data .
  else
    echo "    - skip $V (not found)"
  fi
done

echo "[*] Copying env + compose for reference"
cp "$APP_DIR/.env" "$OUT/old.env" 2>/dev/null || echo "    (no .env found, set it fresh on new box)"
cp "$APP_DIR/docker-compose.yaml" "$OUT/" 2>/dev/null || \
cp "$APP_DIR/docker-compose.yml"  "$OUT/" 2>/dev/null || true

echo "[*] Packing single archive"
tar czf "$HOME/atlas-migrate-$STAMP.tar.gz" -C "$HOME" "atlas-migrate-$STAMP"
rm -rf "$OUT"

echo "[OK] Created: $HOME/atlas-migrate-$STAMP.tar.gz"
echo "    Copy it to the new server, for example:"
echo "    scp -i C:\\Users\\hartm\\strato-private-225-0 $HOME/atlas-migrate-$STAMP.tar.gz atlas@85.215.225.0:~/"
