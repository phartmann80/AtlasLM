"""Private Atlas tool boundary used by the Mastra service.

Every handler derives identity from the signed internal context injected by
AuthMiddleware. The model never supplies user, workspace, or notebook IDs as
authority fields.
"""

from __future__ import annotations

import uuid
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..core.database import get_db
from ..models import (
    AIRun,
    ChatMessage,
    ChatSession,
    Document,
    DocumentChunk,
    StudioOutput,
    StudioOutputCitation,
    Workspace,
    WorkspaceMember,
)
from ..services.rag import RAGService

router = APIRouter(prefix="/internal/atlas/tools", tags=["internal-ai"])


class RetrieveExcerptsRequest(BaseModel):
    query: str = Field(min_length=1, max_length=4000)
    source_ids: list[uuid.UUID] | None = None
    top_k: int = Field(default=8, ge=1, le=24)


class SaveConversationTurnRequest(BaseModel):
    session_id: uuid.UUID
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=100_000)
    citations: list[dict[str, Any]] = Field(default_factory=list)
    runtime: str = "mastra"
    trace_id: str | None = None


class SaveGeneratedOutputRequest(BaseModel):
    output_id: uuid.UUID | None = None
    run_id: uuid.UUID | None = None
    output_type: str = "report"
    title: str = "Atlas Report"
    content: Any
    citations: list[dict[str, Any]] = Field(default_factory=list)
    source_scope: list[uuid.UUID] | None = None
    status: Literal["ready", "failed"] = "ready"
    error: str | None = None
    progress: int = Field(default=100, ge=0, le=100)


class VerifyCitationRequest(BaseModel):
    citations: list[dict[str, Any]] = Field(default_factory=list)


def _context(request: Request) -> dict[str, Any]:
    value = getattr(request.state, "internal_context", None)
    if not value:
        raise HTTPException(status_code=401, detail="Internal context required")
    return value


def _authorized_workspace(request: Request, workspace_id: uuid.UUID, db: Session) -> Workspace:
    context = _context(request)
    user_id = str(context["userId"])
    workspace = db.query(Workspace).filter(Workspace.id == workspace_id).first()
    if not workspace:
        raise HTTPException(status_code=404, detail="Notebook not found")
    is_owner = workspace.user_id == user_id
    is_member = db.query(WorkspaceMember).filter(
        WorkspaceMember.workspace_id == str(workspace_id),
        WorkspaceMember.user_id == user_id,
    ).first() is not None
    if not (is_owner or is_member):
        raise HTTPException(status_code=404, detail="Notebook not found")
    return workspace


def _source_scope(
    request: Request,
    workspace_id: uuid.UUID,
    source_ids: list[uuid.UUID] | None,
    db: Session,
) -> list[Document]:
    _authorized_workspace(request, workspace_id, db)
    query = db.query(Document).filter(
        Document.workspace_id == workspace_id,
        Document.status == "ready",
    )
    if source_ids is not None:
        if not source_ids:
            return []
        query = query.filter(Document.id.in_(source_ids))
    documents = query.order_by(Document.created_at.asc()).all()
    if source_ids is not None and len(documents) != len(set(source_ids)):
        raise HTTPException(status_code=403, detail="One or more sources are not authorized")
    return documents


@router.post("/getNotebookContext")
def get_notebook_context(request: Request, db: Session = Depends(get_db)):
    context = _context(request)
    workspace_id = uuid.UUID(str(context["workspaceId"]))
    workspace = _authorized_workspace(request, workspace_id, db)
    sources = db.query(Document).filter(Document.workspace_id == workspace_id).all()
    return {
        "notebook_id": str(workspace.id),
        "workspace_id": str(workspace.id),
        "name": workspace.name,
        "source_count": len(sources),
        "ready_source_count": sum(source.status == "ready" for source in sources),
        "processing_source_count": sum(source.status in {"pending", "processing"} for source in sources),
        "failed_source_count": sum(source.status == "failed" for source in sources),
    }


@router.post("/listAuthorizedSources")
def list_authorized_sources(request: Request, db: Session = Depends(get_db)):
    context = _context(request)
    workspace_id = uuid.UUID(str(context["workspaceId"]))
    sources = _source_scope(request, workspace_id, None, db)
    return {
        "sources": [
            {
                "id": str(source.id),
                "filename": source.filename,
                "file_type": source.file_type,
                "source_url": source.source_url,
                "status": source.status,
                "created_at": source.created_at.isoformat() if source.created_at else None,
            }
            for source in sources
        ]
    }


@router.post("/retrieveSourceExcerpts")
async def retrieve_source_excerpts(
    body: RetrieveExcerptsRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    context = _context(request)
    workspace_id = uuid.UUID(str(context["workspaceId"]))
    documents = _source_scope(request, workspace_id, body.source_ids, db)
    allowed_ids = [document.id for document in documents]
    chunks = await RAGService(db).retrieve_relevant_chunks(
        workspace_id=workspace_id,
        query=body.query,
        top_k=body.top_k,
        scope_doc_ids=allowed_ids,
    )
    return {
        "excerpts": [
            {
                **chunk,
                "chunk_id": str(chunk["chunk_id"]),
                "document_id": str(chunk["document_id"]),
            }
            for chunk in chunks
        ]
    }


@router.post("/getSourceMetadata")
def get_source_metadata(
    source_ids: list[uuid.UUID],
    request: Request,
    db: Session = Depends(get_db),
):
    context = _context(request)
    workspace_id = uuid.UUID(str(context["workspaceId"]))
    documents = _source_scope(request, workspace_id, source_ids, db)
    return {
        "sources": [
            {
                "id": str(source.id),
                "filename": source.filename,
                "file_type": source.file_type,
                "source_url": source.source_url,
                "status": source.status,
            }
            for source in documents
        ]
    }


@router.post("/saveConversationTurn")
def save_conversation_turn(
    body: SaveConversationTurnRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    context = _context(request)
    workspace_id = uuid.UUID(str(context["workspaceId"]))
    session = db.query(ChatSession).filter(ChatSession.id == body.session_id).first()
    if not session or session.workspace_id != workspace_id:
        raise HTTPException(status_code=404, detail="Conversation not found")
    _authorized_workspace(request, workspace_id, db)
    message = ChatMessage(
        id=uuid.uuid4(),
        session_id=session.id,
        role=body.role,
        content=body.content,
        citations=body.citations,
        runtime=body.runtime,
        trace_id=body.trace_id or context.get("traceId"),
        source_scope={"notebook_id": str(workspace_id)},
    )
    db.add(message)
    db.commit()
    db.refresh(message)
    return {"id": str(message.id), "saved": True}


@router.post("/saveGeneratedOutput")
def save_generated_output(
    body: SaveGeneratedOutputRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    context = _context(request)
    workspace_id = uuid.UUID(str(context["workspaceId"]))
    _authorized_workspace(request, workspace_id, db)
    output = None
    if body.output_id:
        output = db.query(StudioOutput).filter(
            StudioOutput.id == body.output_id,
            StudioOutput.workspace_id == workspace_id,
        ).first()
    if output is None:
        output = StudioOutput(
            id=uuid.uuid4(),
            workspace_id=workspace_id,
            output_type=body.output_type,
            title=body.title,
        )
        db.add(output)
    output.run_id = body.run_id
    output.runtime = "mastra"
    output.content = body.content
    output.source_scope = [str(source_id) for source_id in body.source_scope] if body.source_scope else None
    output.status = body.status
    output.error = body.error
    output.progress = body.progress
    db.query(StudioOutputCitation).filter(
        StudioOutputCitation.studio_output_id == output.id,
    ).delete(synchronize_session=False)
    for citation in body.citations:
        try:
            db.add(StudioOutputCitation(
                studio_output_id=output.id,
                document_id=uuid.UUID(str(citation["document_id"])),
                chunk_id=uuid.UUID(str(citation["chunk_id"])) if citation.get("chunk_id") else None,
                page_number=citation.get("page_number"),
                quote=citation.get("quote"),
                source_url=citation.get("source_url"),
            ))
        except (KeyError, TypeError, ValueError):
            raise HTTPException(status_code=422, detail="Generated output contained an invalid citation")
    db.commit()
    db.refresh(output)
    return {"id": str(output.id), "status": output.status, "saved": True}


@router.post("/verifyCitationReferences")
def verify_citation_references(
    body: VerifyCitationRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    context = _context(request)
    workspace_id = uuid.UUID(str(context["workspaceId"]))
    _authorized_workspace(request, workspace_id, db)
    valid: list[dict[str, Any]] = []
    invalid: list[dict[str, Any]] = []
    for citation in body.citations:
        try:
            chunk_id = uuid.UUID(str(citation.get("chunk_id")))
            row = db.query(DocumentChunk, Document).join(
                Document, DocumentChunk.document_id == Document.id
            ).filter(
                DocumentChunk.id == chunk_id,
                Document.workspace_id == workspace_id,
                Document.status == "ready",
            ).first()
            if row:
                chunk, source = row
                valid.append({
                    **citation,
                    "chunk_id": str(chunk.id),
                    "document_id": str(source.id),
                    "filename": source.filename,
                    "page_number": chunk.page_number,
                    "quote": chunk.content[:500],
                })
            else:
                invalid.append(citation)
        except (ValueError, TypeError):
            invalid.append(citation)
    return {"valid": len(invalid) == 0, "citations": valid, "invalid": invalid}
