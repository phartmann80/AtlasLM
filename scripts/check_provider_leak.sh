#!/bin/sh
# ============================================================
# AtlasLM Patch 008: provider name leak audit (HARD CI GATE).
# Promotes the recurring Patch 006/007 T11 manual grep into a
# build-failing check that cannot be silently skipped.
#
# Exit code is the gate: 0 = clean, 1 = leak found (fails CI/build).
#
# Two ways to run, both fail the build on a leak:
#   docker compose logs --no-color | sh scripts/check_provider_leak.sh
#   sh scripts/check_provider_leak.sh path/to/captured_logs.txt
# ============================================================
set -eu

# Provider and gateway names that must never appear in logs or UI output.
PATTERN='langdock\|openrouter\|openai\|anthropic\|gemini\|api\.openai\|googleapis\|claude\|gpt-'

# Lines that are safe to ignore (env var NAMES in compose, harmless warnings).
# We never want to match the literal env KEY names that legitimately exist.
IGNORE='attribute .version. is obsolete\|LANGDOCK_API_KEY\|OPENROUTER_API_KEY\|LANGDOCK_ENDPOINT_URL\|OPENAI_API_KEY\|GEMINI_API_KEY'

if [ "$#" -ge 1 ]; then
  INPUT=$(cat "$1")
else
  INPUT=$(cat)   # read from stdin (piped docker logs)
fi

MATCHES=$(printf '%s\n' "$INPUT" | grep -i "$PATTERN" 2>/dev/null | grep -v "$IGNORE" || true)

if [ -n "$MATCHES" ]; then
  echo "=================================================="
  echo "PROVIDER LEAK AUDIT FAILED. Build blocked."
  echo "The following lines expose provider or gateway names:"
  echo "--------------------------------------------------"
  printf '%s\n' "$MATCHES"
  echo "=================================================="
  echo "Fix: suppress the leaking logger (e.g. set httpx to WARNING"
  echo "at the service entry points) and re-run. This gate is mandatory."
  exit 1
fi

echo "Provider leak audit passed. No provider or gateway names found."
exit 0
