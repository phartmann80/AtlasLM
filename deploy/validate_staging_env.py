#!/usr/bin/env python3
"""Value-safe staging.env presence and format check.

Reports only SET, EMPTY, MISSING, VALID_FORMAT, or INVALID_FORMAT.
Never prints values, lengths of sensitive values, prefixes, suffixes,
hashes, or derived identifiers.

Usage (on the server, as root, after filling /etc/atlaslm/staging.env):

    python3 deploy/validate_staging_env.py /etc/atlaslm/staging.env

This script does not deploy, does not connect to providers, and does not
read values from the process environment for reporting.
"""

from __future__ import annotations

import argparse
import base64
import json
import re
import sys
from pathlib import Path
from typing import Callable

STATUS_SET = "SET"
STATUS_EMPTY = "EMPTY"
STATUS_MISSING = "MISSING"
STATUS_VALID = "VALID_FORMAT"
STATUS_INVALID = "INVALID_FORMAT"

# Presence classifications used by the first-staging review.
# Values are never printed.
AUTO = "auto"
FIXED = "fixed"
OPTIONAL_EMPTY = "optional_empty"
SUPABASE_URL = "supabase_url"
SUPABASE_ANON = "supabase_anon"
SUPABASE_SERVICE = "supabase_service"
LANGDOCK_ENDPOINT = "langdock_endpoint"
LANGDOCK_MODEL = "langdock_model"
LANGDOCK_CREDENTIAL = "langdock_credential"
GENERATED_SECRET = "generated_secret"

MIN_GENERATED_CHARS = 32
DB_PASSWORD_HEX_CHARS = 64  # openssl rand -hex 32
HOST_RE = re.compile(r"^[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")
SUPABASE_HOST_RE = re.compile(r"^https://[a-z0-9]{20}\.supabase\.co$")
LANGDOCK_ENDPOINT_RE = re.compile(r"^https://api\.langdock\.com/openai/(eu|us)/v1$")
MODEL_RE = re.compile(r"^[A-Za-z0-9._:-]{3,64}$")
B64URL_RE = re.compile(r"^[A-Za-z0-9_-]+$")
PRINTABLE_RE = re.compile(r"^[\x21-\x7E]+$")
HEX40_RE = re.compile(r"^[0-9a-f]{40}$")
HEX64_RE = re.compile(r"^[0-9a-f]{64}$")
# Current Supabase API keys. Prefix checks are internal; never printed.
SB_PUBLISHABLE_RE = re.compile(r"^sb_publishable_[A-Za-z0-9_-]{20,}$")
SB_SECRET_RE = re.compile(r"^sb_secret_[A-Za-z0-9_-]{20,}$")
PUBLIC_NAME_PREFIX = "NEXT_PUBLIC_"
COMPOSE_DB_USER = "atlaslm"
COMPOSE_DB_HOST = "postgres"
COMPOSE_DB_PORT = 5432
COMPOSE_DB_NAME = "atlaslm_db"


def parse_env_file(text: str) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if not key or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        parsed[key] = value
    return parsed


def _b64url_decode(part: str) -> bytes | None:
    if not B64URL_RE.fullmatch(part):
        return None
    pad = "=" * (-len(part) % 4)
    try:
        return base64.urlsafe_b64decode(part + pad)
    except Exception:
        return None


def _jwt_role(value: str) -> str | None:
    parts = value.split(".")
    if len(parts) != 3:
        return None
    if any(not part or _b64url_decode(part) is None for part in parts):
        return None
    payload = _b64url_decode(parts[1])
    if payload is None:
        return None
    try:
        data = json.loads(payload.decode("utf-8"))
    except Exception:
        return None
    role = data.get("role")
    if not isinstance(role, str) or not role:
        return None
    return role


def fmt_nonempty_secret(value: str, minimum: int = MIN_GENERATED_CHARS) -> bool:
    return bool(value) and len(value) >= minimum and PRINTABLE_RE.fullmatch(value) is not None


def fmt_provider_secret(value: str) -> bool:
    return fmt_nonempty_secret(value, minimum=16)


def fmt_exact(expected: str) -> Callable[[str], bool]:
    return lambda value: value == expected


def fmt_host(value: str) -> bool:
    return HOST_RE.fullmatch(value) is not None and ".." not in value


def fmt_supabase_url(value: str) -> bool:
    return SUPABASE_HOST_RE.fullmatch(value.rstrip("/")) is not None


def compose_database_url(password: str) -> str:
    """Match deploy/staging/docker-compose.yaml interpolation (no percent-encoding)."""
    return (
        f"postgresql://{COMPOSE_DB_USER}:{password}"
        f"@{COMPOSE_DB_HOST}:{COMPOSE_DB_PORT}/{COMPOSE_DB_NAME}"
    )


def database_url_round_trips(password: str) -> bool:
    """True only when Compose-style interpolation still parses as that password."""
    from urllib.parse import urlsplit

    try:
        parsed = urlsplit(compose_database_url(password))
        return (
            parsed.scheme == "postgresql"
            and parsed.username == COMPOSE_DB_USER
            and parsed.password == password
            and parsed.hostname == COMPOSE_DB_HOST
            and parsed.port == COMPOSE_DB_PORT
            and parsed.path == f"/{COMPOSE_DB_NAME}"
        )
    except ValueError:
        return False


def fmt_db_password(value: str) -> bool:
    if len(value) != DB_PASSWORD_HEX_CHARS:
        return False
    return HEX64_RE.fullmatch(value) is not None and database_url_round_trips(value)


def is_publishable_api_key(value: str) -> bool:
    return SB_PUBLISHABLE_RE.fullmatch(value) is not None


def is_secret_api_key(value: str) -> bool:
    return SB_SECRET_RE.fullmatch(value) is not None


def is_backend_supabase_secret(value: str) -> bool:
    if not value:
        return False
    if is_secret_api_key(value):
        return True
    return _jwt_role(value) == "service_role"


def fmt_anon_key(value: str) -> bool:
    if is_backend_supabase_secret(value) or is_secret_api_key(value):
        return False
    if is_publishable_api_key(value):
        return True
    return _jwt_role(value) == "anon"


def fmt_service_key(value: str) -> bool:
    if is_publishable_api_key(value) or _jwt_role(value) == "anon":
        return False
    if is_secret_api_key(value):
        return True
    return _jwt_role(value) == "service_role"


def public_names_with_backend_secret(parsed: dict[str, str]) -> bool:
    for name, value in parsed.items():
        if name.startswith(PUBLIC_NAME_PREFIX) and is_backend_supabase_secret(value):
            return True
    return False


def fmt_langdock_endpoint(value: str) -> bool:
    return LANGDOCK_ENDPOINT_RE.fullmatch(value) is not None


def fmt_model(value: str) -> bool:
    return MODEL_RE.fullmatch(value) is not None


def fmt_release_sha(value: str) -> bool:
    return HEX40_RE.fullmatch(value) is not None


def fmt_stripe(value: str) -> bool:
    # Stripe test/live signing secrets use a documented prefix. The check is
    # internal only; the prefix and value are never printed.
    return value.startswith("whsec_") and fmt_provider_secret(value)


def fmt_gateway_url(value: str) -> bool:
    if not value.startswith("https://"):
        return False
    try:
        from urllib.parse import urlparse

        parsed = urlparse(value)
    except Exception:
        return False
    if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
        return False
    host = parsed.hostname or ""
    if host in {"gateway-api.mastra.ai", "api.atlaslm.cloud", "www.atlaslm.cloud"}:
        return False
    return fmt_host(host)


def fmt_timeout(value: str) -> bool:
    return value.isdigit() and 1 <= int(value) <= 120


def fmt_seat_limit(value: str) -> bool:
    return value.isdigit() and 1 <= int(value) <= 100


def fmt_media_mb(value: str) -> bool:
    return value.isdigit() and 1 <= int(value) <= 4096


def fmt_media_seconds(value: str) -> bool:
    return value.isdigit() and 1 <= int(value) <= 86400


def fmt_concurrent_jobs(value: str) -> bool:
    return value.isdigit() and 1 <= int(value) <= 16


def fmt_abs_path(value: str) -> bool:
    return value.startswith("/") and ".." not in value and PRINTABLE_RE.fullmatch(value) is not None


def fmt_gladia_base(value: str) -> bool:
    return value.rstrip("/") == "https://api.gladia.io"


def fmt_gladia_callback(value: str) -> bool:
    return value.rstrip("/") == "https://api.staging.atlaslm.cloud"


CATALOG: list[tuple[str, str, Callable[[str], bool] | None]] = [
    ("ATLAS_RELEASE_SHA", AUTO, fmt_release_sha),
    ("DB_PASSWORD", GENERATED_SECRET, fmt_db_password),
    ("JWT_SECRET", GENERATED_SECRET, fmt_nonempty_secret),
    ("NEXT_PUBLIC_SUPABASE_URL", SUPABASE_URL, fmt_supabase_url),
    ("NEXT_PUBLIC_SUPABASE_ANON_KEY", SUPABASE_ANON, fmt_anon_key),
    ("NEXT_PUBLIC_API_BASE", FIXED, fmt_exact("/api/v1")),
    ("STAGING_FRONTEND_HOST", FIXED, fmt_exact("staging.atlaslm.cloud")),
    ("STAGING_API_HOST", FIXED, fmt_exact("api.staging.atlaslm.cloud")),
    ("FRONTEND_URL", FIXED, fmt_exact("https://staging.atlaslm.cloud")),
    ("APP_URL", FIXED, fmt_exact("https://staging.atlaslm.cloud")),
    ("ATLAS_PUBLIC_BACKEND_URL", FIXED, fmt_exact("https://api.staging.atlaslm.cloud")),
    ("ATLAS_ALLOWED_ORIGINS", FIXED, fmt_exact("https://staging.atlaslm.cloud")),
    ("ATLAS_ENV", FIXED, fmt_exact("staging")),
    ("SUPABASE_SERVICE_ROLE_KEY", SUPABASE_SERVICE, fmt_service_key),
    ("ATLAS_INTERNAL_SIGNING_SECRET", GENERATED_SECRET, fmt_nonempty_secret),
    ("ATLAS_VAULT_KEY", GENERATED_SECRET, fmt_nonempty_secret),
    ("ATLAS_VAULT_KEY_ID", FIXED, fmt_exact("v1")),
    ("ATLAS_ACTIVE_PROVIDER", FIXED, fmt_exact("langdock")),
    ("LANGDOCK_API_KEY", LANGDOCK_CREDENTIAL, fmt_provider_secret),
    ("LANGDOCK_API_CODE", LANGDOCK_CREDENTIAL, fmt_provider_secret),
    ("LANGDOCK_ENDPOINT_URL", LANGDOCK_ENDPOINT, fmt_langdock_endpoint),
    ("LANGDOCK_MODEL", LANGDOCK_MODEL, fmt_model),
    ("MODEL", OPTIONAL_EMPTY, fmt_model),
    ("BLACKBOX_API_KEY", OPTIONAL_EMPTY, fmt_nonempty_secret),
    ("OPENROUTER_API_KEY", OPTIONAL_EMPTY, fmt_nonempty_secret),
    ("OPENAI_API_KEY", OPTIONAL_EMPTY, fmt_nonempty_secret),
    ("GEMINI_API_KEY", OPTIONAL_EMPTY, fmt_nonempty_secret),
    ("STRIPE_WEBHOOK_SECRET", OPTIONAL_EMPTY, fmt_stripe),
    ("GATEWAY_API_URL", OPTIONAL_EMPTY, fmt_gateway_url),
    ("GATEWAY_API_MASTRA_KEY", OPTIONAL_EMPTY, fmt_nonempty_secret),
    ("MASTRA_MODEL", OPTIONAL_EMPTY, fmt_model),
    ("ATLAS_CHAT_RUNTIME", FIXED, fmt_exact("legacy")),
    ("ATLAS_REPORT_RUNTIME", FIXED, fmt_exact("legacy")),
    ("ATLAS_RESEARCH_RUNTIME", FIXED, fmt_exact("legacy")),
    ("ATLAS_MEMORY_MODE", FIXED, fmt_exact("off")),
    ("ATLAS_TRACE_CONTENT", FIXED, fmt_exact("redacted")),
    ("RESEARCH_HTTP_TIMEOUT", FIXED, fmt_timeout),
    ("ATLAS_DEFAULT_SEAT_LIMIT", FIXED, fmt_seat_limit),
    ("GLADIA_API_KEY", OPTIONAL_EMPTY, fmt_provider_secret),
    ("GLADIA_BASE_URL", FIXED, fmt_gladia_base),
    ("GLADIA_CALLBACK_BASE", FIXED, fmt_gladia_callback),
    ("ATLAS_MEDIA_MAX_MB", FIXED, fmt_media_mb),
    ("ATLAS_MEDIA_MAX_SECONDS", FIXED, fmt_media_seconds),
    ("ATLAS_YTDLP_COOKIES", OPTIONAL_EMPTY, fmt_abs_path),
    ("ATLAS_MEDIA_CONCURRENT_JOBS", FIXED, fmt_concurrent_jobs),
    ("ATLAS_MEDIA_DIR", FIXED, fmt_exact("/data/media")),
    ("ATLAS_KOKORO_MODEL", FIXED, fmt_exact("/voices/kokoro-v1.0.onnx")),
    ("ATLAS_KOKORO_VOICES", FIXED, fmt_exact("/voices/voices-v1.0.bin")),
    ("ATLAS_TTS_VOICE_A", FIXED, fmt_exact("af_heart")),
    ("ATLAS_TTS_VOICE_B", FIXED, fmt_exact("am_michael")),
    ("ATLAS_CHROMIUM_BIN", OPTIONAL_EMPTY, fmt_abs_path),
]

FIRST_STAGING_EMPTY_OK = {
    "ATLAS_RELEASE_SHA",
    "LANGDOCK_API_KEY",
    "LANGDOCK_API_CODE",
    "MODEL",
    "BLACKBOX_API_KEY",
    "OPENROUTER_API_KEY",
    "OPENAI_API_KEY",
    "GEMINI_API_KEY",
    "STRIPE_WEBHOOK_SECRET",
    "GATEWAY_API_URL",
    "GATEWAY_API_MASTRA_KEY",
    "MASTRA_MODEL",
    "GLADIA_API_KEY",
    "ATLAS_YTDLP_COOKIES",
    "ATLAS_CHROMIUM_BIN",
}


def presence(name: str, parsed: dict[str, str]) -> str:
    if name not in parsed:
        return STATUS_MISSING
    if parsed[name] == "":
        return STATUS_EMPTY
    return STATUS_SET


def format_status(name: str, kind: str, checker: Callable[[str], bool] | None, parsed: dict[str, str]) -> str:
    status = presence(name, parsed)
    if status == STATUS_MISSING:
        return STATUS_INVALID
    value = parsed.get(name, "")
    if status == STATUS_EMPTY:
        if name in FIRST_STAGING_EMPTY_OK or kind == AUTO:
            return STATUS_VALID
        return STATUS_INVALID
    if checker is None:
        return STATUS_VALID
    return STATUS_VALID if checker(value) else STATUS_INVALID


def report(parsed: dict[str, str]) -> tuple[list[str], int]:
    lines: list[str] = []
    failed = 0
    for name, kind, checker in CATALOG:
        present = presence(name, parsed)
        formatted = format_status(name, kind, checker, parsed)
        lines.append(f"{name} {present}")
        lines.append(f"{name} {formatted}")
        if present == STATUS_MISSING or formatted == STATUS_INVALID:
            failed += 1

    key_set = parsed.get("LANGDOCK_API_KEY", "")
    code_set = parsed.get("LANGDOCK_API_CODE", "")
    cred_present = STATUS_SET if (key_set or code_set) else (
        STATUS_MISSING if ("LANGDOCK_API_KEY" not in parsed and "LANGDOCK_API_CODE" not in parsed) else STATUS_EMPTY
    )
    cred_format = STATUS_VALID if (key_set or code_set) else STATUS_INVALID
    if key_set and not fmt_provider_secret(key_set):
        cred_format = STATUS_INVALID
    if code_set and not fmt_provider_secret(code_set):
        cred_format = STATUS_INVALID
    lines.append(f"LANGDOCK_CREDENTIAL {cred_present}")
    lines.append(f"LANGDOCK_CREDENTIAL {cred_format}")
    if cred_format == STATUS_INVALID or cred_present != STATUS_SET:
        failed += 1

    gateway_url = parsed.get("GATEWAY_API_URL", "")
    gateway_key = parsed.get("GATEWAY_API_MASTRA_KEY", "")
    if bool(gateway_url) != bool(gateway_key):
        lines.append("GATEWAY_PAIR INVALID_FORMAT")
        failed += 1
    else:
        lines.append("GATEWAY_PAIR VALID_FORMAT")

    if public_names_with_backend_secret(parsed):
        lines.append("PUBLIC_SUPABASE_SECRET INVALID_FORMAT")
        failed += 1
    else:
        lines.append("PUBLIC_SUPABASE_SECRET VALID_FORMAT")
    return lines, failed


def catalog_names() -> list[str]:
    return [name for name, _, _ in CATALOG]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Value-safe staging.env validation.")
    parser.add_argument("env_file", help="Path to staging.env. Values are never printed.")
    args = parser.parse_args(argv)
    path = Path(args.env_file)
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        print("ENV_FILE MISSING", file=sys.stderr)
        return 2
    parsed = parse_env_file(text)
    lines, failed = report(parsed)
    print("\n".join(lines))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
