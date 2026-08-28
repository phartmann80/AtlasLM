#!/usr/bin/env bash
# ============================================================
# AtlasLM Patch 008: leak-gate orchestrator.
# Brings the stack up, exercises the LLM paths (ingest + chat +
# studio + scoped synthesis), captures logs, and runs the audit.
# Non-zero exit fails the pipeline. Designed for CI and local use.
# ============================================================
set -euo pipefail
HERE="$(cd "$(dirname "$0")/.." && pwd)"
LOGFILE="${LOGFILE:-/tmp/atlaslm_ci_logs.txt}"

echo "[leak-gate] bringing stack up..."
docker compose up -d --wait || docker compose up -d
sleep 5

# Exercise the provider-touching paths. If the repo ships a smoke runner,
# prefer it; otherwise the gate still audits whatever ran during boot.
if [ -f "run_api_verification.py" ]; then
  echo "[leak-gate] running smoke workflow (run_api_verification.py)..."
  PYTHONIOENCODING=utf-8 python run_api_verification.py || true
fi

echo "[leak-gate] capturing docker logs to ${LOGFILE}..."
# Container stdout/stderr is compose's stdout. Compose CLI interpolation
# warnings go to stderr and must not be mixed into the leak audit.
docker compose logs --no-color > "${LOGFILE}" 2>/tmp/atlaslm_compose_cli.txt || true

echo "[leak-gate] running provider leak audit (build-failing)..."
sh "${HERE}/scripts/check_provider_leak.sh" "${LOGFILE}"
echo "[leak-gate] audit clean."
