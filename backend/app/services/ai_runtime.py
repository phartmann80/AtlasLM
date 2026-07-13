"""Shared runtime primitives for the first AtlasLM agent/workflow slice."""

from __future__ import annotations

import time
import uuid
from typing import Any, Iterable

import httpx
from sqlalchemy.orm import Session

from ..core.config import settings
from ..core.internal_auth import sign_internal_context
from ..core.providers import ProviderError, provider_registry
from ..models import AIRun, AIRunEvent, Document, DocumentChunk, StudioOutput, StudioOutputCitation
from .rag import CITATION_TAG_RE, RAGService


class AIRuntimeError(Exception):
    def __init__(self, message: str, code: str = "ai_runtime_error"):
        super().__init__(message)
        self.code = code


def request_trace_id(request_id: str | None = None) -> str:
    return request_id or f"atlas-{uuid.uuid4().hex}"


def create_run(
    db: Session,
    *,
    user_id: str,
    workspace_id: uuid.UUID,
    agent_id: str,
    workflow_id: str | None,
    runtime: str,
    request_id: str | None,
    idempotency_key: str | None,
    metadata: dict[str, Any] | None = None,
) -> AIRun:
    if idempotency_key:
        existing = db.query(AIRun).filter(
            AIRun.workspace_id == workspace_id,
            AIRun.user_id == user_id,
            AIRun.idempotency_key == idempotency_key,
            AIRun.agent_id == agent_id,
        ).first()
        if existing:
            return existing
    trace_id = request_trace_id(request_id)
    run = AIRun(
        id=uuid.uuid4(),
        user_id=user_id,
        workspace_id=workspace_id,
        notebook_id=workspace_id,
        agent_id=agent_id,
        workflow_id=workflow_id,
        runtime=runtime,
        status="queued",
        request_id=request_id,
        idempotency_key=idempotency_key,
        trace_id=trace_id,
        run_metadata=metadata or {},
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    append_run_event(db, run, "queued", "queued", 0, "Run accepted")
    return run


def append_run_event(
    db: Session,
    run: AIRun,
    event_type: str,
    status: str | None,
    progress: int | None,
    message: str | None,
    payload: dict[str, Any] | None = None,
) -> AIRunEvent:
    event = AIRunEvent(
        id=uuid.uuid4(),
        run_id=run.id,
        event_type=event_type,
        status=status,
        progress=progress,
        message=message,
        payload=payload or {},
        trace_id=run.trace_id,
    )
    db.add(event)
    db.commit()
    return event


def fail_run(db: Session, run: AIRun, message: str, code: str = "generation_failed") -> None:
    run.status = "failed"
    run.error_code = code
    run.error_message = message
    run.latency_ms = int((time.monotonic() - _run_started(run)) * 1000)
    db.commit()
    append_run_event(db, run, "failed", "failed", 100, message, {"error_code": code})


def _run_started(run: AIRun) -> float:
    # A monotonic timer cannot be persisted, so this fallback only prevents a
    # missing latency value. The endpoint records a more precise value when it
    # owns the full request lifecycle.
    return time.monotonic()


def ready_source_chunks(
    db: Session,
    workspace_id: uuid.UUID,
    source_ids: list[uuid.UUID] | None,
    max_chunks: int = 64,
    max_chars: int = 90_000,
) -> list[dict[str, Any]]:
    query = db.query(DocumentChunk, Document).join(
        Document, DocumentChunk.document_id == Document.id
    ).filter(
        Document.workspace_id == workspace_id,
        Document.status == "ready",
    )
    if source_ids is not None:
        if not source_ids:
            return []
        query = query.filter(Document.id.in_(source_ids))
    rows = query.order_by(Document.created_at.asc(), DocumentChunk.chunk_index.asc()).limit(max_chunks).all()
    chunks: list[dict[str, Any]] = []
    used = 0
    for chunk, document in rows:
        if used + len(chunk.content) > max_chars:
            break
        chunks.append({
            "chunk_id": chunk.id,
            "document_id": document.id,
            "filename": document.filename,
            "content": chunk.content,
            "page_number": chunk.page_number,
            "sheet": chunk.sheet,
            "timestamp": chunk.timestamp,
            "source_url": document.source_url,
            "file_type": document.file_type,
        })
        used += len(chunk.content)
    return chunks


def _report_prompt(focus: str | None, length: str) -> str:
    length_rules = {
        "brief": "Keep it to approximately 500 words.",
        "standard": "Write approximately 900 to 1400 words.",
        "deep": "Write a detailed report with enough depth to cover the evidence, without padding.",
    }.get(length, "Write a clear, useful report.")
    focus_rule = f"Focus on this question: {focus}" if focus else "Choose the most useful organizing question from the evidence."
    return (
        "Create a research report using ONLY the provided source blocks. "
        "Start with a clear Markdown title, then an executive summary, key findings, "
        "evidence-based sections, and a conclusion. Every factual claim must include "
        "one or more source tags such as [source_1]. Include an Evidence highlights "
        "section with short exact quotes from the sources, each tagged. If the sources "
        "do not support a conclusion, say so explicitly. Do not invent facts, links, "
        "or recommendations. Do not use em dashes, en dashes, or ellipsis characters.\n\n"
        f"{length_rules}\n{focus_rule}"
    )


async def generate_legacy_report(
    db: Session,
    run: AIRun,
    output: StudioOutput,
    source_ids: list[uuid.UUID] | None,
    focus: str | None,
    length: str,
) -> StudioOutput:
    started = time.monotonic()
    run.status = "running"
    output.status = "processing"
    output.progress = 10
    db.commit()
    append_run_event(db, run, "authorize", "running", 10, "Checking source access")
    chunks = ready_source_chunks(db, run.workspace_id, source_ids)
    if not chunks:
        raise AIRuntimeError(
            "This notebook has no ready sources. Add a source and wait until it is ready before generating a report.",
            "no_ready_sources",
        )
    append_run_event(db, run, "retrieve", "running", 35, f"Loaded {len(chunks)} authorized excerpts")
    rag = RAGService(db)
    system_prompt, mapping = rag.construct_system_prompt(chunks, answer_mode="sources")
    system_prompt = system_prompt + "\n\nYou are generating a persisted AtlasLM Report. Follow the report task exactly."
    prompt = _report_prompt(focus, length)
    llm = provider_registry.get_llm(None)
    append_run_event(db, run, "generate", "running", 55, "Generating the report")
    try:
        content = await llm.generate(prompt, system_prompt=system_prompt)
    except ProviderError as exc:
        raise AIRuntimeError(exc.public_message, "provider_error") from exc
    if not content or not content.strip():
        raise AIRuntimeError("Atlas generated no report content. Please try again.", "empty_output")
    tags = set(CITATION_TAG_RE.findall(content))
    citations = [details for tag, details in mapping.items() if tag in tags]
    if not citations:
        raise AIRuntimeError(
            "Atlas could not verify citations for this report. Please try again.",
            "citation_validation_failed",
        )
    append_run_event(db, run, "validate_citations", "running", 80, f"Verified {len(citations)} source references")
    output.content = content
    output.status = "ready"
    output.error = None
    output.runtime = run.runtime
    output.run_id = run.id
    output.progress = 100
    output.source_scope = [str(source_id) for source_id in source_ids] if source_ids else None
    for citation in citations:
        db.add(StudioOutputCitation(
            studio_output_id=output.id,
            document_id=uuid.UUID(str(citation["document_id"])),
            chunk_id=uuid.UUID(str(citation["chunk_id"])),
            page_number=citation.get("page_number"),
            quote=citation.get("content", "")[:500],
            source_url=citation.get("source_url"),
        ))
    run.status = "completed"
    run.latency_ms = int((time.monotonic() - started) * 1000)
    db.commit()
    append_run_event(db, run, "saved", "completed", 100, "Report saved and ready to reopen")
    return output


async def call_mastra_report(
    *,
    run: AIRun,
    output: StudioOutput,
    request_id: str | None,
    source_ids: list[uuid.UUID] | None,
    focus: str | None,
    length: str,
) -> dict[str, Any]:
    """Call the private Mastra service with a signed Atlas context."""
    context = {
        "userId": run.user_id,
        "workspaceId": str(run.workspace_id),
        "notebookId": str(run.notebook_id),
        "requestId": request_id or run.request_id,
        "traceId": run.trace_id,
        "exp": int(time.time()) + settings.ATLAS_INTERNAL_CONTEXT_TTL_SECONDS,
    }
    encoded, signature = sign_internal_context(context)
    headers = {
        "X-Atlas-Internal-Context": encoded,
        "X-Atlas-Internal-Signature": signature,
        "X-Request-ID": run.trace_id or request_id or "atlas",
    }
    payload = {
        "runId": str(run.id),
        "outputId": str(output.id),
        "sourceIds": [str(source_id) for source_id in source_ids] if source_ids else None,
        "focus": focus,
        "length": length,
        "title": output.title,
    }
    try:
        async with httpx.AsyncClient(timeout=180.0) as client:
            response = await client.post(
                f"{settings.MASTRA_INTERNAL_URL.rstrip('/')}/v1/reports",
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
            return response.json()
    except httpx.HTTPStatusError as exc:
        raise AIRuntimeError("The Atlas research service could not finish this report.", "mastra_http_error") from exc
    except Exception as exc:
        raise AIRuntimeError("The Atlas research service is unavailable. Please try again.", "mastra_unavailable") from exc


async def stream_mastra_chat(
    *,
    run_id: uuid.UUID,
    user_id: str,
    workspace_id: uuid.UUID,
    notebook_id: uuid.UUID,
    request_id: str | None,
    trace_id: str | None,
    session_id: uuid.UUID,
    question: str,
    source_ids: list[uuid.UUID] | None,
    mode: str,
):
    """Proxy Mastra SSE through FastAPI so the browser never sees Mastra."""
    context = {
        "userId": user_id,
        "workspaceId": str(workspace_id),
        "notebookId": str(notebook_id),
        "requestId": request_id,
        "traceId": trace_id,
        "exp": int(time.time()) + settings.ATLAS_INTERNAL_CONTEXT_TTL_SECONDS,
    }
    encoded, signature = sign_internal_context(context)
    headers = {
        "X-Atlas-Internal-Context": encoded,
        "X-Atlas-Internal-Signature": signature,
        "X-Request-ID": trace_id or "atlas",
    }
    payload = {
        "sessionId": str(session_id),
        "question": question,
        "sourceIds": [str(source_id) for source_id in source_ids] if source_ids is not None else None,
        "mode": mode,
        "traceId": trace_id,
    }
    try:
        async with httpx.AsyncClient(timeout=None) as client:
            async with client.stream(
                "POST",
                f"{settings.MASTRA_INTERNAL_URL.rstrip('/')}/v1/chat",
                headers=headers,
                json=payload,
            ) as response:
                response.raise_for_status()
                async for chunk in response.aiter_bytes():
                    yield chunk
    except Exception as exc:
        raise AIRuntimeError("Atlas could not complete the research answer.", "mastra_chat_failed") from exc
