#!/usr/bin/env python3
"""Deployment-hardening tests for staging Compose, atlaslmctl, and migrations."""

from __future__ import annotations

import io
import json
import os
import re
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEPLOY = ROOT / "deploy"
STAGING_COMPOSE = DEPLOY / "staging" / "docker-compose.yaml"
CADDYFILE = DEPLOY / "staging" / "Caddyfile"
FRONTEND_DOCKERFILE = ROOT / "frontend" / "Dockerfile"
PRODUCTION_COMPOSE = ROOT / "docker-compose.yaml"
MANIFEST_PATH = DEPLOY / "migrations.manifest.json"
PRODUCTION_VOLUMES = {"atlaslm_data", "atlaslm_redis", "atlaslm_audio"}
PUBLIC_SERVICES = {"postgres", "redis", "backend", "frontend", "worker", "mastra"}
SHA40 = "a" * 40
CANARY = "STAGING_ENV_CANARY_VALUE_DO_NOT_PRINT"


def load_module(name: str, path: Path):
    from importlib.machinery import SourceFileLoader

    return SourceFileLoader(name, str(path)).load_module()


CTL = load_module("atlaslmctl", DEPLOY / "atlaslmctl")
MIGRATE = load_module("atlaslm_migrate", DEPLOY / "migrate.py")


def parse_compose_services(text: str) -> dict[str, dict]:
    services: dict[str, dict] = {}
    in_services = False
    current = None
    subsection = None
    for raw in text.splitlines():
        if raw.startswith("services:"):
            in_services = True
            current = None
            subsection = None
            continue
        if not in_services:
            continue
        if raw.startswith("volumes:") or raw.startswith("networks:"):
            break
        match = re.match(r"^  ([a-z0-9_-]+):\s*$", raw)
        if match:
            current = match.group(1)
            services[current] = {
                "ports": [],
                "expose": [],
                "volumes": [],
                "networks": [],
                "image": "",
                "healthcheck": False,
                "raw": [],
            }
            subsection = None
            continue
        if current is None:
            continue
        services[current]["raw"].append(raw)
        key = re.match(r"^    ([a-z0-9_]+):", raw)
        if key:
            subsection = key.group(1)
            if subsection == "healthcheck":
                services[current]["healthcheck"] = True
            if subsection == "image":
                services[current]["image"] = raw.split(":", 1)[1].strip()
            continue
        if subsection == "ports" and re.match(r"^\s+-\s+", raw):
            services[current]["ports"].append(raw.split("-", 1)[1].strip().strip('"').strip("'"))
        elif subsection == "expose" and re.match(r"^\s+-\s+", raw):
            services[current]["expose"].append(raw.strip())
        elif subsection == "volumes" and re.match(r"^\s+-\s+", raw):
            services[current]["volumes"].append(raw.split("-", 1)[1].strip())
        elif subsection == "networks" and re.match(r"^\s+-\s+", raw):
            services[current]["networks"].append(raw.split("-", 1)[1].strip())
    return services


def top_level_named_volumes(text: str) -> set[str]:
    names: set[str] = set()
    in_volumes = False
    for raw in text.splitlines():
        if raw.startswith("volumes:"):
            in_volumes = True
            continue
        if in_volumes and raw.startswith("services:"):
            break
        if in_volumes and raw.startswith("networks:"):
            continue
        if in_volumes:
            match = re.match(r"^  ([a-z0-9_]+):\s*$", raw)
            if match:
                names.add(match.group(1))
    return names


class ComposeHardeningTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = STAGING_COMPOSE.read_text(encoding="utf-8")
        cls.services = parse_compose_services(cls.text)
        cls.named_volumes = top_level_named_volumes(cls.text)

    def test_project_name(self) -> None:
        self.assertIn("name: atlaslm-staging", self.text)

    def test_staging_volumes_never_attach_production(self) -> None:
        self.assertTrue(self.named_volumes)
        for volume in self.named_volumes:
            self.assertTrue(volume.startswith("atlaslm_staging_"), volume)
            self.assertNotIn(volume, PRODUCTION_VOLUMES)
        for forbidden in PRODUCTION_VOLUMES:
            self.assertNotRegex(self.text, rf"(^|[^a-z_]){forbidden}([^a-z_]|$)")
        production = PRODUCTION_COMPOSE.read_text(encoding="utf-8")
        for volume in PRODUCTION_VOLUMES:
            self.assertIn(f"  {volume}:", production)

    def test_only_caddy_publishes_public_ports(self) -> None:
        self.assertIn("caddy", self.services)
        self.assertEqual(set(self.services["caddy"]["ports"]), {"80:80", "443:443"})
        for name, service in self.services.items():
            if name == "caddy":
                continue
            self.assertEqual(service["ports"], [], f"{name} must not publish host ports")

    def test_no_public_database_redis_backend_binds(self) -> None:
        for name in PUBLIC_SERVICES:
            self.assertIn(name, self.services)
            self.assertEqual(self.services[name]["ports"], [], name)
            for raw in self.services[name]["raw"]:
                if re.match(r"^    [a-z0-9_]+:", raw):
                    self.assertFalse(raw.strip().startswith("ports:"), name)

    def test_healthchecks_present(self) -> None:
        for name in ("frontend", "backend", "mastra", "postgres", "redis", "worker", "caddy"):
            self.assertTrue(self.services[name]["healthcheck"], name)

    def test_frontend_proxy_uses_compose_backend(self) -> None:
        frontend = "\n".join(self.services["frontend"]["raw"])
        self.assertIn("ATLAS_BACKEND_URL: http://backend:8000", frontend)

    def test_images_require_release_sha(self) -> None:
        for name in ("frontend", "backend", "worker", "mastra"):
            image = self.services[name]["image"]
            self.assertIn("${ATLAS_RELEASE_SHA:?", image)
            self.assertIn("atlaslm-staging-", image)

    def test_searxng_and_extras_disabled(self) -> None:
        self.assertNotIn("docker-compose.searxng", self.text.lower())
        self.assertNotRegex(self.text, r"(?m)^\s+searxng:")
        self.assertNotIn("studio-extra", self.text.lower())
        self.assertNotIn("searxng", self.services)

    def test_caddy_routes(self) -> None:
        caddy = CADDYFILE.read_text(encoding="utf-8")
        self.assertIn("staging.atlaslm.cloud", caddy)
        self.assertIn("api.staging.atlaslm.cloud", caddy)
        self.assertIn("reverse_proxy frontend:3000", caddy)
        self.assertIn("reverse_proxy backend:8000", caddy)

    def test_frontend_dockerfile_build_args_are_public_only(self) -> None:
        text = FRONTEND_DOCKERFILE.read_text(encoding="utf-8")
        self.assertIn("ARG NEXT_PUBLIC_SUPABASE_URL", text)
        self.assertIn("ARG NEXT_PUBLIC_SUPABASE_ANON_KEY", text)
        self.assertIn("ARG NEXT_PUBLIC_API_BASE", text)
        self.assertNotIn("SERVICE_ROLE", text)
        self.assertNotIn("SUPABASE_SERVICE_ROLE_KEY", text)

    def test_networks_match_recommended_model(self) -> None:
        self.assertEqual(self.services["caddy"]["networks"], ["proxy"])
        self.assertEqual(self.services["frontend"]["networks"], ["proxy"])
        self.assertEqual(set(self.services["backend"]["networks"]), {"proxy", "app"})
        for name in ("worker", "mastra", "postgres", "redis"):
            self.assertEqual(self.services[name]["networks"], ["app"], name)

    def test_no_production_health_url(self) -> None:
        self.assertNotIn("https://api.atlaslm.cloud/health", self.text)
        ctl_src = (DEPLOY / "atlaslmctl").read_text(encoding="utf-8")
        self.assertIn("https://api.staging.atlaslm.cloud/health", ctl_src)


class AtlaslmctlTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.env_file = self.tmp / "staging.env"
        self.env_file.write_text(
            f"DB_PASSWORD={CANARY}\nJWT_SECRET={CANARY}\nSUPER_SECRET={CANARY}\n",
            encoding="utf-8",
        )

    def _run(self, argv: list[str]) -> tuple[int, str, str]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = CTL.main(argv)
        return code, stdout.getvalue(), stderr.getvalue()

    def _common(self) -> list[str]:
        return [
            "--dry-run",
            "--app-root",
            str(ROOT),
            "--env-file",
            str(self.env_file),
            "--project",
            "atlaslm-staging",
        ]

    def test_exact_sha_validation(self) -> None:
        for bad in ("abc", "a" * 39, "a" * 41, "g" * 40, "A" * 39 + "G"):
            code, _, err = self._run([*self._common(), "staging", "deploy", bad])
            self.assertEqual(code, 2, bad)
            self.assertIn("40-character", err)
        code, out, err = self._run([*self._common(), "staging", "deploy", SHA40])
        self.assertEqual(code, 0, err)
        self.assertIn("staging deploy complete", out)

    def test_uppercase_sha_normalized(self) -> None:
        sha = "ABCDEF" + "a" * 34
        self.assertEqual(len(sha), 40)
        code, out, err = self._run([*self._common(), "staging", "deploy", sha])
        self.assertEqual(code, 0, err)
        self.assertIn(sha.lower(), out)

    def test_rollback_selects_immutable_tags_without_rebuild(self) -> None:
        code, out, err = self._run([*self._common(), "staging", "rollback", SHA40])
        self.assertEqual(code, 0, err)
        self.assertIn("--no-build", out)
        self.assertIn("--pull", out)
        self.assertIn("never", out)
        for line in out.splitlines():
            if not line.startswith("+"):
                continue
            tokens = line.split()
            self.assertNotIn("build", tokens)
            self.assertIn("--no-build", tokens)
        self.assertIn("immutable tags", out)
        cmd = CTL.rollback_command(["docker", "compose"])
        self.assertEqual(cmd[cmd.index("up") :], ["up", "-d", "--no-build", "--pull", "never", "frontend", "backend", "worker", "mastra", "caddy"])
        self.assertNotIn("build", cmd[cmd.index("up") :])

    def test_production_commands_rejected(self) -> None:
        for argv in (
            ["production", "deploy", SHA40],
            ["prod", "status"],
            ["staging", "deploy", SHA40, "production"],
            [*self._common(), "--env-file", "/etc/atlaslm/production.env", "staging", "status"],
        ):
            code, _, err = self._run(argv)
            self.assertEqual(code, 2, argv)
            self.assertIn("rejected argument", err)

    def test_unknown_action_rejected(self) -> None:
        code, _, err = self._run([*self._common(), "staging", "restart"])
        self.assertNotEqual(code, 0)
        self.assertTrue(err)

    def test_production_health_url_rejected(self) -> None:
        code, _, err = self._run(
            [
                *self._common(),
                "--health-url",
                "https://api.atlaslm.cloud/health",
                "staging",
                "deploy",
                SHA40,
            ]
        )
        self.assertEqual(code, 2)
        self.assertIn("production health URL", err)

    def test_deploy_uses_parameterized_staging_health_url(self) -> None:
        code, out, err = self._run([*self._common(), "staging", "deploy", SHA40])
        self.assertEqual(code, 0, err)
        self.assertIn("https://api.staging.atlaslm.cloud/health", out)
        self.assertNotIn("https://api.atlaslm.cloud/health", out)
        self.assertIn("-p atlaslm-staging", out)
        self.assertIn("deploy/staging/docker-compose.yaml", out)

    def test_logs_and_errors_never_print_env_file(self) -> None:
        code, out, err = self._run([*self._common(), "staging", "logs", "backend"])
        self.assertEqual(code, 0, err)
        combined = out + err + (DEPLOY / "atlaslmctl").read_text(encoding="utf-8")
        self.assertNotIn(CANARY, out)
        self.assertNotIn(CANARY, err)
        self.assertNotIn("print(env_file", combined)
        self.assertNotIn("read_text", combined)
        self.assertNotRegex(combined, r"cat .*\.env")

    def test_sanitize_log_line(self) -> None:
        line = CTL.sanitize_log_line("Authorization=secret-token JWT_SECRET=abc bearer abcdef")
        self.assertNotIn("secret-token", line)
        self.assertNotIn("abcdef", line)
        self.assertIn("<redacted>", line)

    def test_frontend_is_built_and_started_on_deploy(self) -> None:
        code, out, err = self._run([*self._common(), "staging", "deploy", SHA40])
        self.assertEqual(code, 0, err)
        build_lines = [line for line in out.splitlines() if line.startswith("+") and " build " in line]
        self.assertTrue(build_lines)
        tokens = build_lines[0].split()
        build_at = tokens.index("build")
        self.assertEqual(tokens[build_at + 1 : build_at + 4], ["frontend", "backend", "mastra"])
        self.assertIn("frontend", out)
        self.assertIn("caddy", out)

    def test_unapproved_compose_files_rejected(self) -> None:
        production_compose = str(ROOT / "docker-compose.yaml")
        searxng = str(ROOT / "docker" / "docker-compose.searxng.yml")
        cases = (
            [*self._common(), "-f", production_compose, "staging", "status"],
            [*self._common(), "--file", searxng, "staging", "status"],
            [*self._common(), f"--file={production_compose}", "staging", "status"],
            [*self._common(), "staging", "logs", "docker-compose.searxng"],
        )
        for argv in cases:
            code, _, err = self._run(argv)
            self.assertEqual(code, 2, argv)
            self.assertIn("unapproved compose file", err)
        with self.assertRaises(CTL.AtlasLMCtlError):
            CTL.approved_compose_file(ROOT / "docker-compose.yaml")
        approved = CTL.approved_compose_file(ROOT / "deploy" / "staging" / "docker-compose.yaml")
        self.assertEqual(approved.name, "docker-compose.yaml")
        previous = os.environ.get("COMPOSE_FILE")
        os.environ["COMPOSE_FILE"] = production_compose
        try:
            code, _, err = self._run([*self._common(), "staging", "status"])
        finally:
            if previous is None:
                os.environ.pop("COMPOSE_FILE", None)
            else:
                os.environ["COMPOSE_FILE"] = previous
        self.assertEqual(code, 2)
        self.assertIn("unapproved compose file", err)

    def test_unapproved_project_rejected(self) -> None:
        code, _, err = self._run(
            [
                "--dry-run",
                "--app-root",
                str(ROOT),
                "--env-file",
                str(self.env_file),
                "--project",
                "other-project",
                "staging",
                "status",
            ]
        )
        self.assertEqual(code, 2)
        self.assertIn("unapproved compose project", err)



class MigrationTests(unittest.TestCase):
    def test_manifest_order_not_glob_order(self) -> None:
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        ids = [item["id"] for item in manifest["migrations"]]
        paths = [item["path"] for item in manifest["migrations"]]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertNotIn("migrations/010_ai_runtime.down.sql", paths)
        globbed = sorted(p.name for p in (ROOT / "migrations").glob("004*.sql"))
        self.assertEqual(globbed[0], "004_audio_overviews.sql")
        canvas = next(i for i, p in enumerate(paths) if p.endswith("004_patch_006_canvas_and_flags.sql"))
        audio = next(i for i, p in enumerate(paths) if p.endswith("004_audio_overviews.sql"))
        self.assertLess(canvas, audio)
        team = next(i for i, p in enumerate(paths) if p.endswith("007_team_membership.sql"))
        patch007 = next(i for i, p in enumerate(paths) if p.endswith("patch_007_synthesis_and_sources.sql"))
        self.assertLess(patch007, team)
        glob_all = sorted(p.name for p in (ROOT / "migrations").glob("*.sql") if not p.name.endswith(".down.sql"))
        self.assertLess(glob_all.index("007_team_membership.sql"), glob_all.index("patch_007_synthesis_and_sources.sql"))

    def test_dry_run_prints_manifest_order(self) -> None:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = MIGRATE.main(["--dry-run", "--root", str(ROOT), "--manifest", str(MANIFEST_PATH)])
        self.assertEqual(code, 0, stderr.getvalue())
        lines = [line for line in stdout.getvalue().splitlines() if line.strip()]
        self.assertTrue(lines[0].startswith("000_enable_vector"))
        ids = [line.split()[0] for line in lines]
        self.assertEqual(ids, [item["id"] for item in json.loads(MANIFEST_PATH.read_text())["migrations"]])

    def test_duplicate_ids_rejected(self) -> None:
        tmp = Path(tempfile.mkdtemp())
        sql = tmp / "one.sql"
        sql.write_text("SELECT 1;", encoding="utf-8")
        manifest = tmp / "manifest.json"
        manifest.write_text(
            json.dumps(
                {
                    "schema_table": "atlaslm_schema_migrations",
                    "migrations": [
                        {"id": "dup", "path": "one.sql"},
                        {"id": "dup", "path": "one.sql"},
                    ],
                }
            ),
            encoding="utf-8",
        )
        with self.assertRaises(MIGRATE.MigrationError):
            MIGRATE.load_manifest(tmp, manifest)

    def test_apply_records_and_fails_atomically(self) -> None:
        tmp = Path(tempfile.mkdtemp())
        (tmp / "a.sql").write_text("SELECT 1;", encoding="utf-8")
        (tmp / "b.sql").write_text("SELECT boom;", encoding="utf-8")
        manifest = tmp / "manifest.json"
        manifest.write_text(
            json.dumps(
                {
                    "schema_table": "atlaslm_schema_migrations",
                    "migrations": [
                        {"id": "a", "path": "a.sql"},
                        {"id": "b", "path": "b.sql"},
                    ],
                }
            ),
            encoding="utf-8",
        )

        class FakeCursor:
            def __init__(self, conn: "FakeConn") -> None:
                self.conn = conn

            def execute(self, sql: str, params=None) -> None:
                self.conn.executed.append((sql, params))
                if params is None and "boom" in sql:
                    raise RuntimeError("sql failed")

            def fetchall(self):
                return list(self.conn.registry)

            def __enter__(self):
                return self

            def __exit__(self, *args) -> bool:
                return False

        class FakeConn:
            def __init__(self) -> None:
                self.autocommit = True
                self.executed: list = []
                self.commits = 0
                self.rollbacks = 0
                self.closed = False
                self.registry: list = []

            def cursor(self):
                return FakeCursor(self)

            def commit(self) -> None:
                for sql, params in reversed(self.executed):
                    if params is not None and "INSERT" in sql.upper():
                        row = (params[0], params[2])
                        if row not in self.registry:
                            self.registry.append(row)
                        break
                self.commits += 1

            def rollback(self) -> None:
                self.rollbacks += 1

            def close(self) -> None:
                self.closed = True

        conn = FakeConn()
        with self.assertRaises(MIGRATE.MigrationError) as raised:
            MIGRATE.apply_migrations("postgresql://unused", tmp, manifest, conn=conn)
        self.assertIn("failed applying b", str(raised.exception))
        self.assertGreaterEqual(conn.rollbacks, 1)
        self.assertEqual(conn.registry, [("a", MIGRATE.file_sha256(tmp / "a.sql"))])
        self.assertNotIn("postgresql://unused", str(raised.exception))

    def test_checksum_mismatch_fails_without_reapply(self) -> None:
        tmp = Path(tempfile.mkdtemp())
        (tmp / "a.sql").write_text("SELECT 1;", encoding="utf-8")
        manifest = tmp / "manifest.json"
        manifest.write_text(
            json.dumps(
                {
                    "schema_table": "atlaslm_schema_migrations",
                    "migrations": [{"id": "a", "path": "a.sql"}],
                }
            ),
            encoding="utf-8",
        )

        class FakeCursor:
            def __init__(self, conn: "FakeConn") -> None:
                self.conn = conn

            def execute(self, sql: str, params=None) -> None:
                return None

            def fetchall(self):
                return [("a", "deadbeef")]

            def __enter__(self):
                return self

            def __exit__(self, *args) -> bool:
                return False

        class FakeConn:
            def __init__(self) -> None:
                self.autocommit = True
                self.rollbacks = 0

            def cursor(self):
                return FakeCursor(self)

            def commit(self) -> None:
                return None

            def rollback(self) -> None:
                self.rollbacks += 1

            def close(self) -> None:
                return None

        conn = FakeConn()
        with self.assertRaises(MIGRATE.MigrationError) as raised:
            MIGRATE.apply_migrations("postgresql://unused", tmp, manifest, conn=conn)
        self.assertIn("checksum mismatch", str(raised.exception))
        self.assertGreaterEqual(conn.rollbacks, 1)


if __name__ == "__main__":
    unittest.main()
