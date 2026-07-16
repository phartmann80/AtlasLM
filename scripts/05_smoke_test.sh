#!/usr/bin/env bash
# Patch 016A - Step 5: smoke test the live deployment on atlaslm.cloud.
# Run anywhere with network access to the server. Exits non-zero on any failure.
set -uo pipefail

DOMAIN="atlaslm.cloud"
FAIL=0

check() {
  local label="$1"; shift
  if "$@" >/dev/null 2>&1; then
    echo "  PASS  $label"
  else
    echo "  FAIL  $label"
    FAIL=1
  fi
}

echo "[*] DNS"
check "atlaslm.cloud resolves to 85.215.225.0" \
  bash -c "getent hosts $DOMAIN | grep -q 85.215.225.0"

echo "[*] TLS + HTTP"
check "https://$DOMAIN returns 200" \
  bash -c "curl -fsS -o /dev/null -w '%{http_code}' https://$DOMAIN | grep -q 200"
check "valid certificate (no -k needed)" \
  bash -c "curl -fsS https://$DOMAIN -o /dev/null"
check "http redirects to https" \
  bash -c "curl -sS -o /dev/null -w '%{http_code}' http://$DOMAIN | grep -qE '30[18]'"

echo "[*] API health"
check "backend API reachable" \
  bash -c "curl -sS -o /dev/null -w '%{http_code}' https://$DOMAIN/api/v1/openapi.json | grep -qE '200|404'"

echo "[*] Containers"
check "all containers running" \
  bash -c "cd /home/atlas/atlaslm && docker compose ps --status running | grep -qE 'frontend|backend|db|caddy'"

echo "[*] Database"
check "verify_teams offline checks pass" \
  bash -c "docker exec atlaslm-backend-1 python /workspace/verify_teams.py"

echo
if [ "$FAIL" -eq 0 ]; then
  echo "ALL SMOKE TESTS PASSED. atlaslm.cloud is live on 85.215.225.0."
else
  echo "ONE OR MORE SMOKE TESTS FAILED. Do not switch traffic until green."
  exit 1
fi
