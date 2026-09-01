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
PUBLISHABLE = "sb_publishable_" + ("p" * 32)
SECRET_API = "sb_secret_" + ("s" * 32)
HEX_DB = "ab" * 32
GEN = "A" * 32
LANGDOCK = "B" * 24
FORBIDDEN_OUTPUT = (
    CANARY,
    ANON,
    SERVICE,
    PUBLISHABLE,
    SECRET_API,
    HEX_DB,
    GEN,
    LANGDOCK,
    "eyJ",
    "whsec_",
    "sb_publishable_",
    "sb_secret_",
    "service_role",
    "ortmzzdfkwidvuolczqa",
    "ciinvalidproject",
)


def valid_env(**overrides: str) -> str:
    rows = {
        "ATLAS_RELEASE_SHA": "",
        "DB_PASSWORD": HEX_DB,
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


def assert_output_safe(test: unittest.TestCase, *parts: str) -> None:
    combined = "".join(parts)
    for token in FORBIDDEN_OUTPUT:
        test.assertNotIn(token, combined)
    test.assertNotRegex(combined, r"\b32\b")
    test.assertNotRegex(combined, r"\b64\b")


class CatalogSyncTests(unittest.TestCase):
    def test_catalog_matches_env_example(self) -> None:
        example = VALIDATE.parse_env_file(EXAMPLE.read_text(encoding="utf-8"))
        self.assertEqual(list(example), VALIDATE.catalog_names())


class OutputSafetyTests(unittest.TestCase):
    def test_valid_first_staging_env(self) -> None:
        code, out, err = run_file(valid_env())
        self.assertEqual(code, 0, "expected a valid first-staging fixture to pass")
        assert_output_safe(self, out, err)
        self.assertIn("LANGDOCK_CREDENTIAL SET", out)
        self.assertIn("LANGDOCK_CREDENTIAL VALID_FORMAT", out)
        self.assertIn("GATEWAY_PAIR VALID_FORMAT", out)
        self.assertIn("PUBLIC_SUPABASE_SECRET VALID_FORMAT", out)
        self.assertIn("ATLAS_RELEASE_SHA EMPTY", out)
        self.assertIn("ATLAS_RELEASE_SHA VALID_FORMAT", out)
        self.assertIn("STRIPE_WEBHOOK_SECRET EMPTY", out)
        self.assertIn("GATEWAY_API_URL EMPTY", out)
        self.assertIn("DB_PASSWORD SET", out)
        self.assertIn("DB_PASSWORD VALID_FORMAT", out)

    def test_canary_never_printed(self) -> None:
        text = valid_env(JWT_SECRET=CANARY)
        code, out, err = run_file(text)
        self.assertEqual(code, 0, "canary JWT_SECRET fixture should remain valid")
        assert_output_safe(self, out, err)
        self.assertNotIn("DO_NOT_PRINT", out + err)
        self.assertNotIn("CANARY", out + err)

    def test_example_template_is_not_ready(self) -> None:
        code, out, err = run_file(EXAMPLE.read_text(encoding="utf-8"))
        self.assertEqual(code, 1)
        self.assertIn("DB_PASSWORD EMPTY", out)
        self.assertIn("DB_PASSWORD INVALID_FORMAT", out)
        self.assertIn("LANGDOCK_CREDENTIAL EMPTY", out)
        assert_output_safe(self, out, err)

    def test_service_role_rejected_as_anon(self) -> None:
        code, out, err = run_file(valid_env(NEXT_PUBLIC_SUPABASE_ANON_KEY=SERVICE))
        self.assertEqual(code, 1)
        self.assertIn("NEXT_PUBLIC_SUPABASE_ANON_KEY SET", out)
        self.assertIn("NEXT_PUBLIC_SUPABASE_ANON_KEY INVALID_FORMAT", out)
        self.assertIn("PUBLIC_SUPABASE_SECRET INVALID_FORMAT", out)
        assert_output_safe(self, out, err)

    def test_production_mastra_gateway_rejected(self) -> None:
        code, out, _ = run_file(
            valid_env(
                GATEWAY_API_URL="https://gateway-api.mastra.ai",
                GATEWAY_API_MASTRA_KEY=GEN,
            )
        )
        self.assertEqual(code, 1)
        self.assertIn("GATEWAY_API_URL INVALID_FORMAT", out)
        assert_output_safe(self, out)
        self.assertNotIn("gateway-api.mastra.ai", out)

    def test_gateway_pair_must_be_together(self) -> None:
        code, out, _ = run_file(valid_env(GATEWAY_API_URL="https://staging-gateway.example.test"))
        self.assertEqual(code, 1)
        self.assertIn("GATEWAY_PAIR INVALID_FORMAT", out)
        assert_output_safe(self, out)

    def test_missing_file(self) -> None:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = VALIDATE.main(["/tmp/atlaslm-missing-staging.env"])
        self.assertEqual(code, 2)
        self.assertIn("ENV_FILE MISSING", stderr.getvalue())
        self.assertEqual(stdout.getvalue(), "")


class SupabaseKeyFormatTests(unittest.TestCase):
    def _accepts(self, **overrides: str) -> None:
        code, out, err = run_file(valid_env(**overrides))
        self.assertEqual(code, 0, "supported key combination should pass")
        self.assertIn("NEXT_PUBLIC_SUPABASE_ANON_KEY VALID_FORMAT", out)
        self.assertIn("SUPABASE_SERVICE_ROLE_KEY VALID_FORMAT", out)
        self.assertIn("PUBLIC_SUPABASE_SECRET VALID_FORMAT", out)
        assert_output_safe(self, out, err)

    def _rejects_anon(self, value: str) -> None:
        code, out, err = run_file(valid_env(NEXT_PUBLIC_SUPABASE_ANON_KEY=value))
        self.assertEqual(code, 1, "unsupported public key should fail")
        self.assertIn("NEXT_PUBLIC_SUPABASE_ANON_KEY SET", out)
        self.assertIn("NEXT_PUBLIC_SUPABASE_ANON_KEY INVALID_FORMAT", out)
        assert_output_safe(self, out, err)

    def _rejects_service(self, value: str) -> None:
        code, out, err = run_file(valid_env(SUPABASE_SERVICE_ROLE_KEY=value))
        self.assertEqual(code, 1, "unsupported backend key should fail")
        self.assertIn("SUPABASE_SERVICE_ROLE_KEY SET", out)
        self.assertIn("SUPABASE_SERVICE_ROLE_KEY INVALID_FORMAT", out)
        assert_output_safe(self, out, err)

    def test_legacy_jwt_pair_accepted(self) -> None:
        self._accepts()

    def test_current_api_key_pair_accepted(self) -> None:
        self._accepts(NEXT_PUBLIC_SUPABASE_ANON_KEY=PUBLISHABLE, SUPABASE_SERVICE_ROLE_KEY=SECRET_API)

    def test_legacy_anon_with_current_secret_accepted(self) -> None:
        self._accepts(SUPABASE_SERVICE_ROLE_KEY=SECRET_API)

    def test_current_publishable_with_legacy_service_accepted(self) -> None:
        self._accepts(NEXT_PUBLIC_SUPABASE_ANON_KEY=PUBLISHABLE)

    def test_rejects_service_jwt_in_public_slot(self) -> None:
        self._rejects_anon(SERVICE)
        code, out, err = run_file(valid_env(NEXT_PUBLIC_SUPABASE_ANON_KEY=SERVICE))
        self.assertIn("PUBLIC_SUPABASE_SECRET INVALID_FORMAT", out)
        assert_output_safe(self, out, err)

    def test_rejects_secret_api_key_in_public_slot(self) -> None:
        self._rejects_anon(SECRET_API)
        code, out, err = run_file(valid_env(NEXT_PUBLIC_SUPABASE_ANON_KEY=SECRET_API))
        self.assertIn("PUBLIC_SUPABASE_SECRET INVALID_FORMAT", out)
        assert_output_safe(self, out, err)

    def test_rejects_anon_jwt_in_service_slot(self) -> None:
        self._rejects_service(ANON)

    def test_rejects_publishable_key_in_service_slot(self) -> None:
        self._rejects_service(PUBLISHABLE)

    def test_rejects_backend_secret_in_any_public_variable(self) -> None:
        code, out, err = run_file(valid_env(NEXT_PUBLIC_API_BASE=SECRET_API))
        self.assertEqual(code, 1, "secret material in a public variable should fail")
        self.assertIn("NEXT_PUBLIC_API_BASE INVALID_FORMAT", out)
        self.assertIn("PUBLIC_SUPABASE_SECRET INVALID_FORMAT", out)
        assert_output_safe(self, out, err)


class DatabaseUrlSafetyTests(unittest.TestCase):
    def test_hex_password_round_trips_in_compose_url(self) -> None:
        password = HEX_DB
        ok = VALIDATE.database_url_round_trips(password)
        self.assertTrue(ok, "URI-safe hex password must round-trip in DATABASE_URL")
        code, out, err = run_file(valid_env(DB_PASSWORD=password))
        self.assertEqual(code, 0, "hex DB_PASSWORD should be accepted")
        self.assertIn("DB_PASSWORD VALID_FORMAT", out)
        assert_output_safe(self, out, err)

    def test_uri_special_characters_do_not_round_trip(self) -> None:
        # These reserved characters make urllib split userinfo/host/query/fragment
        # incorrectly, so Compose interpolation cannot be trusted.
        broken = (
            "aa/" + ("b" * 62),
            "aa?" + ("b" * 62),
            "aa#" + ("b" * 62),
        )
        for password in broken:
            self.assertFalse(
                VALIDATE.database_url_round_trips(password),
                "reserved URI characters must not silently parse as DATABASE_URL userinfo",
            )
            code, out, err = run_file(valid_env(DB_PASSWORD=password))
            self.assertEqual(code, 1, "URI-unsafe DB_PASSWORD should be rejected")
            self.assertIn("DB_PASSWORD SET", out)
            self.assertIn("DB_PASSWORD INVALID_FORMAT", out)
            assert_output_safe(self, out, err)
            self.assertNotIn(password, out + err)

    def test_other_userinfo_reserved_characters_are_still_rejected(self) -> None:
        # urllib may keep these in userinfo, but they remain unsafe for libpq and
        # for first-@ parsers. Hex-only validation must still reject them.
        reserved = (
            "aa@" + ("b" * 62),
            "aa:" + ("b" * 62),
            "aa%" + ("b" * 62),
        )
        for password in reserved:
            code, out, err = run_file(valid_env(DB_PASSWORD=password))
            self.assertEqual(code, 1, "non-hex DB_PASSWORD should be rejected")
            self.assertIn("DB_PASSWORD INVALID_FORMAT", out)
            assert_output_safe(self, out, err)
            self.assertNotIn(password, out + err)

    def test_standard_base64_with_slash_is_rejected(self) -> None:
        import base64
        import os

        raw = os.urandom(32)
        b64 = base64.b64encode(raw).decode("ascii")
        if "/" not in b64:
            b64 = b64[:10] + "/" + b64[11:]
        self.assertFalse(
            VALIDATE.database_url_round_trips(b64),
            "standard Base64 with a slash must not silently produce a valid DATABASE_URL",
        )
        code, out, err = run_file(valid_env(DB_PASSWORD=b64))
        self.assertEqual(code, 1, "base64 DB_PASSWORD should be rejected")
        self.assertIn("DB_PASSWORD INVALID_FORMAT", out)
        assert_output_safe(self, out, err)
        self.assertNotIn(b64, out + err)

    def test_other_generated_secrets_may_remain_base64(self) -> None:
        import base64
        import os

        b64 = base64.b64encode(os.urandom(48)).decode("ascii")
        code, out, err = run_file(
            valid_env(
                JWT_SECRET=b64,
                ATLAS_INTERNAL_SIGNING_SECRET=b64,
                ATLAS_VAULT_KEY=b64,
            )
        )
        self.assertEqual(code, 0, "non-URI secrets may still be Base64")
        assert_output_safe(self, out, err)
        self.assertNotIn(b64, out + err)


class MastraGatewayDefaultTests(unittest.TestCase):
    def test_mastra_does_not_default_to_production_gateway(self) -> None:
        text = (ROOT / "mastra" / "src" / "index.ts").read_text(encoding="utf-8")
        self.assertNotIn("gateway-api.mastra.ai", text)
        self.assertIn("/health", text)


if __name__ == "__main__":
    unittest.main()
