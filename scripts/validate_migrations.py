"""Static safety gate for additive AtlasLM migrations."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
UP = ROOT / "migrations" / "010_ai_runtime_vertical_slice.sql"


def main() -> None:
    sql = UP.read_text(encoding="utf-8").lower()
    required = [
        "create table if not exists ai_runs",
        "create table if not exists ai_run_events",
        "create table if not exists workspace_layouts",
        "alter table chat_messages add column if not exists runtime",
        "alter table studio_outputs add column if not exists run_id",
        "alter table studio_output_citations add column if not exists chunk_id",
    ]
    missing = [item for item in required if item not in sql]
    if missing:
        raise SystemExit("Migration safety check failed, missing: " + ", ".join(missing))
    if "drop table" in sql or "drop column" in sql or "truncate " in sql or "delete from" in sql:
        raise SystemExit("Migration safety check failed, destructive SQL found")
    print("migration safety check: PASS")


if __name__ == "__main__":
    main()
