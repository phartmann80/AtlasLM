#!/usr/bin/env python3
"""Trust-boundary tests for privileged atlaslmctl."""

from __future__ import annotations

import io
import os
import shutil
import stat
import subprocess
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from test_deploy_hardening import CTL, ROOT, CANARY

GIT = shutil.which("git") or "/usr/bin/git"


def git_env(home: Path) -> dict[str, str]:
    return {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": str(home),
        "GIT_AUTHOR_NAME": "AtlasLM Test",
        "GIT_AUTHOR_EMAIL": "atlaslm-test@example.invalid",
        "GIT_COMMITTER_NAME": "AtlasLM Test",
        "GIT_COMMITTER_EMAIL": "atlaslm-test@example.invalid",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_TERMINAL_PROMPT": "0",
        "LANG": "C",
    }


def run_git(args: list[str], *, cwd: Path, env: dict[str, str]) -> str:
    completed = subprocess.run(
        [GIT, *args],
        cwd=str(cwd),
        env=env,
        check=True,
        text=True,
        capture_output=True,
    )
    return completed.stdout.strip()


def seed_application_tree(dest: Path) -> None:
    ignore = shutil.ignore_patterns("__pycache__", "*.pyc", ".git")
    shutil.copytree(ROOT / "deploy", dest / "deploy", ignore=ignore)
    shutil.copytree(ROOT / "migrations", dest / "migrations", ignore=ignore)
    (dest / "docker").mkdir()
    shutil.copytree(ROOT / "docker" / "init", dest / "docker" / "init", ignore=ignore)
    for part in ("frontend", "backend", "mastra"):
        (dest / part).mkdir()
        shutil.copy2(ROOT / part / "Dockerfile", dest / part / "Dockerfile")


def build_origin_repo(base: Path) -> tuple[Path, str, str]:
    origin = base / "origin.git"
    work = base / "origin-work"
    work.mkdir()
    seed_application_tree(work)
    env = git_env(base)
    run_git(["init", "-b", "main"], cwd=work, env=env)
    run_git(["add", "."], cwd=work, env=env)
    run_git(["-c", "user.email=atlaslm-test@example.invalid", "-c", "user.name=AtlasLM Test", "commit", "-m", "main"], cwd=work, env=env)
    main_sha = run_git(["rev-parse", "HEAD"], cwd=work, env=env)
    run_git(["checkout", "-b", "evil"], cwd=work, env=env)
    (work / "evil.txt").write_text("unapproved\n", encoding="utf-8")
    run_git(["add", "evil.txt"], cwd=work, env=env)
    run_git(["-c", "user.email=atlaslm-test@example.invalid", "-c", "user.name=AtlasLM Test", "commit", "-m", "evil"], cwd=work, env=env)
    evil_sha = run_git(["rev-parse", "HEAD"], cwd=work, env=env)
    run_git(["checkout", "main"], cwd=work, env=env)
    run_git(["clone", "--bare", str(work), str(origin)], cwd=base, env=env)
    return origin, main_sha, evil_sha


class TrustBoundaryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.origin, self.main_sha, self.evil_sha = build_origin_repo(self.tmp)
        self.root = self.tmp / "srv" / "atlaslm"
        (self.root / "incoming").mkdir(parents=True)
        (self.root / "releases").mkdir()
        (self.root / "runtime").mkdir()
        self.env_file = self.tmp / "staging.env"
        self.env_file.write_text(
            f"DB_PASSWORD={CANARY}\nJWT_SECRET={CANARY}\nSUPER_SECRET={CANARY}\n",
            encoding="utf-8",
        )
        self.log: list[list[str]] = []
        self.cfg = CTL.TrustedConfig(
            root=self.root,
            env_file=self.env_file,
            git_remote=str(self.origin),
            approved_ref="refs/heads/main",
            project=CTL.FIXED_PROJECT,
            health_url=CTL.FIXED_HEALTH_URL,
            required_uid=os.getuid(),
            required_gid=os.getgid(),
            dry_run=True,
            command_log=self.log,
            existing_images=frozenset(),
            git_bin=GIT,
            docker_bin="/usr/bin/docker",
        )
        CTL._test_config = self.cfg
        CTL._test_force_privileged = True
        os.chmod(self.root / "incoming", 0o0777)
        (self.root / "incoming" / "docker-compose.yaml").write_text(
            "name: pwned\nservices: {}\n",
            encoding="utf-8",
        )
        (self.root / "incoming" / "Dockerfile").write_text("FROM scratch\n", encoding="utf-8")
        (self.root / "incoming" / "migrate.py").write_text("print('pwned')\n", encoding="utf-8")
        self._poison_env()

    def tearDown(self) -> None:
        CTL._test_config = None
        CTL._test_force_privileged = None
        for key in list(os.environ):
            if key.startswith("ATLASLM") or key in {
                "COMPOSE_FILE",
                "DOCKER_HOST",
                "GIT_DIR",
                "PYTHONPATH",
            }:
                if key in self._saved_env:
                    os.environ[key] = self._saved_env[key]
                else:
                    os.environ.pop(key, None)

    def _poison_env(self) -> None:
        self._saved_env = {
            key: os.environ[key]
            for key in (
                "ATLASLM_APP_ROOT",
                "ATLASLM_REPO",
                "ATLASLM_STAGING_ENV_FILE",
                "ATLASLM_COMPOSE_PROJECT",
                "ATLASLM_HEALTH_URL",
                "COMPOSE_FILE",
                "DOCKER_HOST",
                "GIT_DIR",
                "PYTHONPATH",
                "PATH",
            )
            if key in os.environ
        }
        incoming = str(self.root / "incoming")
        os.environ["ATLASLM_APP_ROOT"] = incoming
        os.environ["ATLASLM_REPO"] = incoming
        os.environ["ATLASLM_STAGING_ENV_FILE"] = str(self.root / "incoming" / "staging.env")
        os.environ["ATLASLM_COMPOSE_PROJECT"] = "pwned"
        os.environ["ATLASLM_HEALTH_URL"] = "https://api.atlaslm.cloud/health"
        os.environ["COMPOSE_FILE"] = str(self.root / "incoming" / "docker-compose.yaml")
        os.environ["DOCKER_HOST"] = "tcp://127.0.0.1:1"
        os.environ["GIT_DIR"] = incoming
        os.environ["PYTHONPATH"] = incoming

    def _run(self, argv: list[str]) -> tuple[int, str, str]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = CTL.main(argv)
        return code, stdout.getvalue(), stderr.getvalue()

    def test_caller_overrides_ignored_and_incoming_not_executed(self) -> None:
        env = CTL.clean_subprocess_env(self.cfg, {"ATLAS_RELEASE_SHA": self.main_sha})
        self.assertEqual(env["PATH"], CTL.FIXED_PATH)
        self.assertNotIn("PYTHONPATH", env)
        self.assertNotIn("DOCKER_HOST", env)
        self.assertNotIn("GIT_DIR", env)
        self.assertNotIn("COMPOSE_FILE", env)
        self.assertNotIn("ATLASLM_APP_ROOT", env)
        self.assertNotEqual(env.get("PATH"), str(self.root / "incoming"))
        code, out, err = self._run(["staging", "deploy", self.main_sha])
        self.assertEqual(code, 0, err)
        self.assertNotIn(CANARY, out)
        self.assertNotIn(CANARY, err)
        joined = " ".join(" ".join(cmd) for cmd in self.log)
        self.assertIn(str(self.root / "releases" / self.main_sha / "deploy" / "staging" / "docker-compose.yaml"), joined)
        self.assertNotIn(str(self.root / "incoming"), joined)
        self.assertIn("build frontend backend mastra", joined)
        self.assertIn(CTL.FIXED_HEALTH_URL, joined)
        self.assertNotIn("https://api.atlaslm.cloud/health", joined)
        release = self.root / "releases" / self.main_sha
        self.assertTrue(release.is_dir())
        self.assertEqual(CTL.git_commit_sha(release, self.cfg), self.main_sha)
        self.assertTrue((self.root / "runtime" / "staging").is_symlink())
        self.assertEqual((self.root / "runtime" / "staging").resolve(), release.resolve())

    def test_writable_compose_replacement_rejected(self) -> None:
        code, _, err = self._run(["staging", "deploy", self.main_sha])
        self.assertEqual(code, 0, err)
        release = self.root / "releases" / self.main_sha
        compose = release / "deploy" / "staging" / "docker-compose.yaml"
        os.chmod(compose, 0o0666)
        with self.assertRaises(CTL.AtlasLMCtlError) as raised:
            CTL.verify_release_tree(release, self.main_sha, self.cfg)
        self.assertIn("writable", str(raised.exception))

    def test_writable_dockerfile_and_build_context_rejected(self) -> None:
        code, _, err = self._run(["staging", "deploy", self.main_sha])
        self.assertEqual(code, 0, err)
        release = self.root / "releases" / self.main_sha
        dockerfile = release / "frontend" / "Dockerfile"
        os.chmod(dockerfile, 0o0666)
        with self.assertRaises(CTL.AtlasLMCtlError) as raised:
            CTL.verify_release_tree(release, self.main_sha, self.cfg)
        self.assertIn("writable", str(raised.exception))

    def test_writable_migration_code_rejected(self) -> None:
        code, _, err = self._run(["staging", "deploy", self.main_sha])
        self.assertEqual(code, 0, err)
        release = self.root / "releases" / self.main_sha
        os.chmod(release / "deploy" / "migrate.py", 0o0777)
        with self.assertRaises(CTL.AtlasLMCtlError):
            CTL.verify_release_tree(release, self.main_sha, self.cfg)
        os.chmod(release / "deploy" / "migrate.py", 0o0755)
        sql = next((release / "migrations").glob("*.sql"))
        os.chmod(sql, 0o0666)
        with self.assertRaises(CTL.AtlasLMCtlError):
            CTL.verify_release_tree(release, self.main_sha, self.cfg)

    def test_symlink_escape_rejected(self) -> None:
        code, _, err = self._run(["staging", "deploy", self.main_sha])
        self.assertEqual(code, 0, err)
        release = self.root / "releases" / self.main_sha
        caddy = release / "deploy" / "staging" / "Caddyfile"
        caddy.unlink()
        caddy.symlink_to(self.root / "incoming" / "docker-compose.yaml")
        with self.assertRaises(CTL.AtlasLMCtlError) as raised:
            CTL.verify_release_tree(release, self.main_sha, self.cfg)
        self.assertIn("symlink escape", str(raised.exception))

    def test_fake_sha_labeling_impossible(self) -> None:
        code, _, err = self._run(["staging", "deploy", self.main_sha])
        self.assertEqual(code, 0, err)
        release = self.root / "releases" / self.main_sha
        with self.assertRaises(CTL.AtlasLMCtlError) as raised:
            CTL.verify_release_tree(release, self.evil_sha, self.cfg, require_dirname=False)
        self.assertIn("HEAD", str(raised.exception))

    def test_sha_not_reachable_from_approved_ref_rejected(self) -> None:
        code, _, err = self._run(["staging", "deploy", self.evil_sha])
        self.assertEqual(code, 2, err)
        self.assertIn("not reachable from the approved ref", err)
        self.assertFalse((self.root / "releases" / self.evil_sha).exists())

    def test_rollback_refuses_missing_images_and_unverified_releases(self) -> None:
        code, _, err = self._run(["staging", "rollback", self.main_sha])
        self.assertEqual(code, 2, err)
        self.assertIn("verified release not found", err)
        code, _, err = self._run(["staging", "deploy", self.main_sha])
        self.assertEqual(code, 0, err)
        self.log.clear()
        code, _, err = self._run(["staging", "rollback", self.main_sha])
        self.assertEqual(code, 2, err)
        self.assertIn("required immutable images are missing", err)
        self.cfg.existing_images = frozenset(CTL.image_names(self.main_sha))
        self.log.clear()
        code, out, err = self._run(["staging", "rollback", self.main_sha])
        self.assertEqual(code, 0, err)
        joined = " ".join(" ".join(cmd) for cmd in self.log)
        self.assertIn("--no-build", joined)
        self.assertIn("never", joined)
        self.assertNotRegex(joined, r"\sbuild\s")
        self.assertIn(str(self.root / "releases" / self.main_sha / "deploy" / "staging" / "docker-compose.yaml"), joined)
        self.assertNotIn(str(self.root / "incoming"), joined)

    def test_status_and_logs_use_verified_release_not_writable_tree(self) -> None:
        code, _, err = self._run(["staging", "status"])
        self.assertEqual(code, 2, err)
        incoming_link = self.root / "runtime" / "staging"
        incoming_link.symlink_to(self.root / "incoming")
        code, _, err = self._run(["staging", "status"])
        self.assertEqual(code, 2, err)
        self.assertTrue("outside trusted releases" in err or "refusing" in err or "verified release" in err)
        incoming_link.unlink()
        code, _, err = self._run(["staging", "deploy", self.main_sha])
        self.assertEqual(code, 0, err)
        self.log.clear()
        code, _, err = self._run(["staging", "status"])
        self.assertEqual(code, 0, err)
        joined = " ".join(" ".join(cmd) for cmd in self.log)
        self.assertIn(str(self.root / "releases" / self.main_sha / "deploy" / "staging" / "docker-compose.yaml"), joined)
        self.assertNotIn("/incoming/", joined)
        self.log.clear()
        code, out, err = self._run(["staging", "logs"])
        self.assertEqual(code, 0, err)
        self.assertNotIn(CANARY, out + err)

    def test_production_remains_rejected(self) -> None:
        code, _, err = self._run(["production", "deploy", self.main_sha])
        self.assertEqual(code, 2)
        self.assertIn("rejected argument", err)

    def test_git_clone_uses_http11(self) -> None:
        self.cfg.dry_run = False
        release = CTL.obtain_release(self.main_sha, self.cfg)
        self.assertTrue(release.is_dir())
        clone_cmds = [cmd for cmd in self.log if len(cmd) >= 4 and cmd[3] == "clone"]
        self.assertEqual(len(clone_cmds), 1, self.log)
        expected_tmp = str(self.root / "releases" / f".tmp-{self.main_sha}-{os.getpid()}")
        self.assertEqual(
            clone_cmds[0],
            [
                self.cfg.git_bin,
                "-c",
                "http.version=HTTP/1.1",
                "clone",
                "--quiet",
                str(self.origin),
                expected_tmp,
            ],
        )

    def test_every_git_command_has_http11(self) -> None:
        code, _, err = self._run(["staging", "deploy", self.main_sha])
        self.assertEqual(code, 0, err)
        git_cmds = [cmd for cmd in self.log if cmd and cmd[0] == self.cfg.git_bin]
        self.assertTrue(git_cmds)
        for cmd in git_cmds:
            self.assertEqual(cmd[1:3], ["-c", "http.version=HTTP/1.1"], cmd)

    def test_clone_failure_surfaces_stderr_tail(self) -> None:
        self.cfg.git_remote = str(self.tmp / "does-not-exist.git")
        with self.assertRaises(CTL.AtlasLMCtlError) as raised:
            CTL.cmd_deploy(self.main_sha)
        message = str(raised.exception)
        self.assertIn("exit 128:", message)
        self.assertIn(" :: ", message)
        self.assertNotIn("\n", message)
        self.assertTrue(message.split(" :: ", 1)[1].strip())

    def test_non_git_failure_stays_opaque(self) -> None:
        self.cfg.dry_run = False
        error = subprocess.CalledProcessError(
            1,
            [self.cfg.docker_bin],
            stderr=f"line 2: unexpected character in {CANARY}\n",
        )
        compose = [
            self.cfg.docker_bin,
            "compose",
            "--env-file",
            str(self.cfg.env_file),
            "ps",
        ]
        with patch.object(CTL.subprocess, "run", side_effect=error):
            with self.assertRaises(CTL.AtlasLMCtlError) as raised:
                CTL._run(compose, cfg=self.cfg, git=False)
        message = str(raised.exception)
        self.assertNotIn(CANARY, message)
        self.assertNotIn(" :: ", message)
        self.assertIn("command failed with exit 1:", message)

    def test_failure_redacts_token_and_gladia_key(self) -> None:
        error = subprocess.CalledProcessError(
            1,
            [self.cfg.git_bin],
            stderr="token=abc123\nx-gladia-key: zzz\n",
        )
        with patch.object(CTL.subprocess, "run", side_effect=error):
            with self.assertRaises(CTL.AtlasLMCtlError) as raised:
                CTL._run([self.cfg.git_bin, "status"], cfg=self.cfg, git=True)
        message = str(raised.exception)
        self.assertNotIn("abc123", message)
        self.assertNotIn("zzz", message)
        self.assertIn("<redacted>", message)


if __name__ == "__main__":
    unittest.main()
