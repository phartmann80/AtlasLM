#!/usr/bin/env python3
"""Deterministic AtlasLM SQL migrator. Order comes from the manifest, not globs.

Atomicity is per migration, not across the whole manifest. Each unapplied
migration runs in its own transaction: the SQL script and the registry insert
either both commit or both roll back. Previously committed migrations stay
applied if a later migration fails. Whole-manifest atomicity is not used
because several historical scripts are operational DDL plus diagnostic
statements rather than a single verified transaction-compatible batch.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path

MANIFEST_NAME = "migrations.manifest.json"
DOWN_SUFFIX = ".down.sql"
SCHEMA_TABLE_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class MigrationError(Exception):
    pass


def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def default_manifest_path() -> Path:
    return Path(__file__).resolve().parent / MANIFEST_NAME


def load_manifest(root: Path, manifest_path: Path | None = None) -> dict:
    path = Path(manifest_path) if manifest_path else default_manifest_path()
    if not path.is_file():
        raise MigrationError("migration manifest not found")
    data = json.loads(path.read_text(encoding="utf-8"))
    table = data.get("schema_table", "")
    if not SCHEMA_TABLE_RE.fullmatch(str(table)):
        raise MigrationError("invalid schema_table in migration manifest")
    ids = [item["id"] for item in data["migrations"]]
    if len(ids) != len(set(ids)):
        raise MigrationError("migration manifest contains duplicate ids")
    paths = [item["path"] for item in data["migrations"]]
    if len(paths) != len(set(paths)):
        raise MigrationError("migration manifest contains duplicate paths")
    for item in data["migrations"]:
        if item["path"].endswith(DOWN_SUFFIX):
            raise MigrationError(f"down migration listed in apply manifest: {item['path']}")
        full = root / item["path"]
        if not full.is_file():
            raise MigrationError(f"missing migration file: {item['path']}")
    return data


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def planned_migrations(root: Path, manifest_path: Path | None = None) -> list[dict]:
    manifest = load_manifest(root, manifest_path)
    planned = []
    for item in manifest["migrations"]:
        path = root / item["path"]
        planned.append(
            {
                "id": item["id"],
                "path": item["path"],
                "checksum": file_sha256(path),
                "sql": path.read_text(encoding="utf-8"),
            }
        )
    return planned


def connect(database_url: str):
    import psycopg2

    return psycopg2.connect(database_url)


def ensure_registry(cursor, table: str) -> None:
    cursor.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {table} (
            id TEXT PRIMARY KEY,
            path TEXT NOT NULL,
            checksum TEXT NOT NULL,
            applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )


def applied_rows(cursor, table: str) -> dict[str, str]:
    cursor.execute(f"SELECT id, checksum FROM {table}")
    return {row[0]: row[1] for row in cursor.fetchall()}


def execute_script(cursor, sql: str) -> None:
    # psycopg2 uses pyformat; raw SQL files may contain LIKE '%'.
    cursor.execute(sql.replace("%", "%%"))


def apply_migrations(
    database_url: str,
    root: Path | None = None,
    manifest_path: Path | None = None,
    conn=None,
) -> list[str]:
    root = root or repo_root()
    manifest = load_manifest(root, manifest_path)
    table = manifest["schema_table"]
    planned = planned_migrations(root, manifest_path)
    owns_connection = conn is None
    if conn is None:
        conn = connect(database_url)
    conn.autocommit = False
    applied: list[str] = []
    current_id = None
    try:
        with conn.cursor() as cursor:
            ensure_registry(cursor, table)
            conn.commit()
            existing = applied_rows(cursor, table)
            for item in planned:
                current_id = item["id"]
                if item["id"] in existing:
                    if existing[item["id"]] != item["checksum"]:
                        raise MigrationError(
                            f"checksum mismatch for already-applied migration {item['id']}"
                        )
                    continue
                execute_script(cursor, item["sql"])
                cursor.execute(
                    f"INSERT INTO {table} (id, path, checksum) VALUES (%s, %s, %s)",
                    (item["id"], item["path"], item["checksum"]),
                )
                conn.commit()
                applied.append(item["id"])
    except MigrationError:
        conn.rollback()
        raise
    except Exception:
        conn.rollback()
        ident = current_id or "registry"
        raise MigrationError(f"failed applying {ident}") from None
    finally:
        if owns_connection:
            conn.close()
    return applied


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Apply AtlasLM SQL migrations in manifest order.")
    parser.add_argument("--database-url", default=os.environ.get("DATABASE_URL", ""))
    parser.add_argument("--root", default=str(repo_root()))
    parser.add_argument("--manifest", default=str(default_manifest_path()))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    try:
        planned = planned_migrations(Path(args.root), Path(args.manifest))
        if args.dry_run:
            for item in planned:
                print(f"{item['id']} {item['path']}")
            return 0
        if not args.database_url:
            raise MigrationError("DATABASE_URL is required")
        applied = apply_migrations(
            args.database_url,
            Path(args.root),
            Path(args.manifest),
        )
        print(f"applied {len(applied)} migrations")
        return 0
    except MigrationError as exc:
        print(f"migration failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
