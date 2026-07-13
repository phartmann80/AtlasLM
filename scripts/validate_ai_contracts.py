"""Dependency-free contract gate for the AtlasLM first vertical slice."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def require(path: Path, *needles: str) -> None:
    content = path.read_text(encoding="utf-8")
    missing = [needle for needle in needles if needle not in content]
    if missing:
        raise SystemExit(f"{path}: missing {', '.join(missing)}")


def main() -> None:
    require(
        ROOT / "backend/app/api/internal_ai.py",
        '"/getNotebookContext"',
        '"/listAuthorizedSources"',
        '"/retrieveSourceExcerpts"',
        '"/getSourceMetadata"',
        '"/saveConversationTurn"',
        '"/saveGeneratedOutput"',
        '"/verifyCitationReferences"',
        "_authorized_workspace",
    )
    require(
        ROOT / "backend/app/core/config.py",
        "ATLAS_CHAT_RUNTIME",
        "ATLAS_REPORT_RUNTIME",
        "ATLAS_RESEARCH_RUNTIME",
        "ATLAS_MEMORY_MODE",
        "ATLAS_TRACE_CONTENT",
    )
    require(
        ROOT / "backend/app/api/endpoints.py",
        'output_type == "report"',
        "create_run(",
        "generate_legacy_report(",
        "call_mastra_report(",
        'ATLAS_CHAT_RUNTIME == "mastra"',
    )
    require(
        ROOT / "mastra/src/index.ts",
        "notebook-research-agent",
        "notebook-report-workflow",
        "verifyCitationReferences",
        "saveGeneratedOutput",
    )
    print("AI contract gate: PASS")


if __name__ == "__main__":
    main()
