#!/usr/bin/env python3
"""Value-safe staging.env validator tests. Fixtures never appear in output."""

from __future__ import annotations

import io
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEPLOY = ROOT / "deploy"
EXAMPLE = DEPLOY / "staging" / "env.example"

from importlib.machinery import SourceFileLoader

VALIDATE = SourceFileLoader("validate_staging_env", str(DEPLOY / "validate_staging_env.py")).load_module()

CANARY = "STAGING_ENV_CANARY_VALUE_DO_NOT_PRINT_OR_HASH"
ANON = (
    "eyJhbGciOiJFUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImNpaW52YWxpZHByb2plY3QiLCJyb2xlIjoiYW5vbiJ9."
    "sig"
)
SERVICE = (
    "eyJhbGciOiJFUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImNpaW52YWxpZHByb2plY3QiLCJyb2xlIjoic2VydmljZV9yb2xlIn0."
    "sig"
)
GEN = "A" * 32
LANGDOCK = "B" * 24


def valid_env(**overrides: str) -> str:
    rows = {
        "ATLAS_RELEASE_SHA": "",
        "DB_PASSWORD": GEN,
        "JWT_SECRET": GEN,
        "NEXT_PUBLIC_SUPABASE_URL": "https://aaaaaaaaaaaaaaaaaaaa.supabase.co",
        "NEXT_PUBLIC_SUPABASE_ANON_KEY": ANON,
        "NEXT_PUBLIC_API_BASE": "/api/v1",
        "STAGING_FRONTEND_HOST": "staging.atlaslm.cloud",
        "STAGING_API_HOST": "api.staging.atlaslm.cloud",
        "FRONTEND_URL": "https://staging.atlaslm.cloud",
        "APP_URL": "https://staging.atlaslm.cloud",
        "ATLAS_PUBLIC_BACKEND_URL": "https://api.staging.atlaslm.cloud",
        "ATLAS_ALLOWED_ORIGINS": "https://staging.atlaslm.cloud",
        "ATLAS_ENV": "staging",
        "SUPABASE_SERVICE_ROLE_KEY": SERVICE,
        "ATLAS_INTERNAL_SIGNING_SECRET": GEN,
        "ATLAS_VAULT_KEY": GEN,
        "ATLAS_VAULT_KEY_ID": "v1",
        "ATLAS_ACTIVE_PROVIDER": "langdock",
        "LANGDOCK_API_KEY": "",
        "LANGDOCK_API_CODE": LANGDOCK,
        "LANGDOCK_ENDPOINT_URL": "https://api.langdock.com/openai/eu/v1",
        "LANGDOCK_MODEL": "gpt-5-mini",
        "MODEL": "",
        "BLACKBOX_API_KEY": "",
        "OPENROUTER_API_KEY": "",
        "OPENAI_API_KEY": "",
        "GEMINI_API_KEY": "",
        "STRIPE_WEBHOOK_SECRET": "",
        "GATEWAY_API_URL": "",
        "GATEWAY_API_MASTRA_KEY": "",
        "MASTRA_MODEL": "",
        "ATLAS_CHAT_RUNTIME": "legacy",
        "ATLAS_REPORT_RUNTIME": "legacy",
        "ATLAS_RESEARCH_RUNTIME": "legacy",
        "ATLAS_MEMORY_MODE": "off",
        "ATLAS_TRACE_CONTENT": "redacted",
        "RESEARCH_HTTP_TIMEOUT": "12",
        "ATLAS_DEFAULT_SEAT_LIMIT": "5",
    }
    rows.update(overrides)
    return "\n".join(f"{key}={value}" for key, value in rows.items()) + "\n"


def run_file(text: str) -> tuple[int, str, str]:
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".env", delete=False) as handle:
        handle.write(text)
        path = handle.name
    stdout = io.StringIO()
    stderr = io.StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        code = VALIDATE.main([path])
    return code, stdout.getvalue(), stderr.getvalue()


class CatalogSyncTests(unittest.TestCase):
    def test_catalog_matches_env_example(self) -> None:
        example = VALIDATE.parse_env_file(EXAMPLE.read_text(encoding="utf-8"))
        self.assertEqual(list(example), VALIDATE.catalog_names())


class OutputSafetyTests(unittest.TestCase):
    def test_valid_first_staging_env(self) -> None:
        code, out, err = run_file(valid_env())
        self.assertEqual(code, 0, out + err)
        self.assertNotIn(CANARY, out + err)
        self.assertNotIn(ANON, out)
        self.assertNotIn(SERVICE, out)
        self.assertNotIn(GEN, out)
        self.assertNotIn(LANGDOCK, out)
        self.assertNotIn("whsec_", out)
        self.assertNotIn("eyJ", out)
        self.assertNotRegex(out, r"\b32\b")
        self.assertIn("LANGDOCK_CREDENTIAL SET", out)
        self.assertIn("LANGDOCK_CREDENTIAL VALID_FORMAT", out)
        self.assertIn("GATEWAY_PAIR VALID_FORMAT", out)
        self.assertIn("ATLAS_RELEASE_SHA EMPTY", out)
        self.assertIn("ATLAS_RELEASE_SHA VALID_FORMAT", out)
        self.assertIn("STRIPE_WEBHOOK_SECRET EMPTY", out)
        self.assertIn("GATEWAY_API_URL EMPTY", out)

    def test_canary_never_printed(self) -> None:
        text = valid_env(DB_PASSWORD=CANARY, JWT_SECRET=CANARY)
        code, out, err = run_file(text)
        self.assertEqual(code, 0)
        combined = out + err
        self.assertNotIn(CANARY, combined)
        self.assertNotIn("DO_NOT_PRINT", combined)
        self.assertNotIn("CANARY", combined)

    def test_example_template_is_not_ready(self) -> None:
        code, out, err = run_file(EXAMPLE.read_text(encoding="utf-8"))
        self.assertEqual(code, 1)
        self.assertIn("DB_PASSWORD EMPTY", out)
        self.assertIn("DB_PASSWORD INVALID_FORMAT", out)
        self.assertIn("LANGDOCK_CREDENTIAL EMPTY", out)
        self.assertNotRegex(out, r"sk-|eyJ|whsec_")

    def test_service_role_rejected_as_anon(self) -> None:
        code, out, _ = run_file(valid_env(NEXT_PUBLIC_SUPABASE_ANON_KEY=SERVICE))
        self.assertEqual(code, 1)
        self.assertIn("NEXT_PUBLIC_SUPABASE_ANON_KEY SET", out)
        self.assertIn("NEXT_PUBLIC_SUPABASE_ANON_KEY INVALID_FORMAT", out)
        self.assertNotIn(SERVICE, out)

    def test_production_mastra_gateway_rejected(self) -> None:
        code, out, _ = run_file(
            valid_env(
                GATEWAY_API_URL="https://gateway-api.mastra.ai",
                GATEWAY_API_MASTRA_KEY=GEN,
            )
        )
        self.assertEqual(code, 1)
        self.assertIn("GATEWAY_API_URL INVALID_FORMAT", out)
        self.assertNotIn("gateway-api.mastra.ai", out)

    def test_gateway_pair_must_be_together(self) -> None:
        code, out, _ = run_file(valid_env(GATEWAY_API_URL="https://staging-gateway.example.test"))
        self.assertEqual(code, 1)
        self.assertIn("GATEWAY_PAIR INVALID_FORMAT", out)

    def test_missing_file(self) -> None:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = VALIDATE.main(["/tmp/atlaslm-missing-staging.env"])
        self.assertEqual(code, 2)
        self.assertIn("ENV_FILE MISSING", stderr.getvalue())
        self.assertEqual(stdout.getvalue(), "")


class MastraGatewayDefaultTests(unittest.TestCase):
    def test_mastra_does_not_default_to_production_gateway(self) -> None:
        text = (ROOT / "mastra" / "src" / "index.ts").read_text(encoding="utf-8")
        self.assertNotIn("gateway-api.mastra.ai", text)
        self.assertIn("/health", text)


if __name__ == "__main__":
    unittest.main()
