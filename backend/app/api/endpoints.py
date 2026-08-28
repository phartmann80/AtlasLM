import uuid
import asyncio
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
from pydantic import BaseModel
import json
import re

from ..core.database import get_db
from ..core.config import settings
from ..models import Workspace, Document, DocumentChunk, ChatSession, ChatMessage, WorkspaceGraphEdge, CanvasPosition, UserProfile, SynthesisNode, SynthesisInput, AIRun, AIRunEvent, WorkspaceLayout
from ..schemas import (
    WorkspaceCreate, WorkspaceOut, DocumentOut, 
    ChatSessionCreate, ChatSessionOut, ChatSessionDetailsOut,
    ChatMessageCreate, URLIngestRequest, TextIngestRequest,
    GraphEdgeCreate, GraphEdgeOut, NodePositionUpdate,
    OnboardingFlagsOut, OnboardingFlagsUpdate,
    SynthesisNodeCreate, SynthesisNodeUpdate, SynthesisNodeOut, SynthesisInputCreate
)
from ..schemas import ReportCreate, AIRunOut, AIRunEventOut, WorkspaceLayoutOut, WorkspaceLayoutUpdate
from ..services.youtube_extract import (
    extract_youtube_transcript, YouTubeExtractError, extract_video_id,
)
from ..services.ingest.youtube_loader import load_youtube
from ..services.transcription_language import normalize_transcription_language
from ..services.pipeline import DocumentPipeline
from ..services.rag import RAGService
from ..core.providers import provider_registry, ProviderError
from ..services.jobs import enqueue_ingestion_job, enqueue_studio_job, redis_healthy
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.encoders import jsonable_encoder
from ..services.studio import StudioService, OUTPUT_TYPES
from ..models import StudioOutput, StudioOutputCitation
from ..schemas import StudioOutputCreate, StudioOutputOut, StudioCitationOut
from ..services.research.service import DeepResearchService
from ..services.research import jobs as research_jobs
from ..services.ai_runtime import (
    AIRuntimeError,
    append_run_event,
    call_mastra_report,
    create_run,
    generate_legacy_report,
    request_trace_id,
    stream_mastra_chat,
)
from pydantic import BaseModel

_research = DeepResearchService()


router = APIRouter()

# -- Helpers ------------------------------------------------------------------

def current_user_id(request: Request) -> str:
    """Extract the authenticated user's sub claim from the request state."""
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required"
        )
    uid = getattr(user, "sub", None) or user.get("sub") if isinstance(user, dict) else None
    if not uid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token: missing sub claim"
        )
    return uid


def _get_owned_workspace(workspace_id: uuid.UUID, user_id: str, db: Session) -> Workspace:
    """Fetch a workspace owned by this user, or raise 404."""
    ws = db.query(Workspace).filter(
        Workspace.id == workspace_id,
        Workspace.user_id == user_id,
    ).first()
    if not ws:
        raise HTTPException(status_code=404, detail="Workspace not found")
    return ws


def _get_owned_document(document_id: uuid.UUID, user_id: str, db: Session) -> Document:
    """Fetch a document in a workspace owned by this user, or raise 404."""
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    try:
        _get_owned_workspace(doc.workspace_id, user_id, db)
    except HTTPException as exc:
        if exc.status_code == 404:
            raise HTTPException(status_code=404, detail="Document not found")
        raise
    return doc


def _get_owned_session(session_id: uuid.UUID, user_id: str, db: Session) -> ChatSession:
    session = db.query(ChatSession).filter(ChatSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Chat session not found")
    try:
        _get_owned_workspace(session.workspace_id, user_id, db)
    except HTTPException as exc:
        if exc.status_code == 404:
            raise HTTPException(status_code=404, detail="Chat session not found")
        raise
    return session


def _request_idempotency_key(request: Request) -> str | None:
    key = (
        request.headers.get("Idempotency-Key")
        or request.headers.get("X-Idempotency-Key")
        or ""
    ).strip()
    if not key:
        return None
    if len(key) > 255:
        raise HTTPException(status_code=400, detail="Idempotency key is too long.")
    return key


def _existing_idempotent_document(
    db: Session,
    workspace_id: uuid.UUID,
    idempotency_key: str | None,
) -> Document | None:
    if not idempotency_key:
        return None
    return (
        db.query(Document)
        .filter(
            Document.workspace_id == workspace_id,
            Document.idempotency_key == idempotency_key,
        )
        .first()
    )


def _normalize_public_url(raw_url: str) -> str:
    url = raw_url.strip()
    if not url:
        raise HTTPException(status_code=400, detail="URL is required")
    if not re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", url):
        url = f"https://{url}"
    if not url.lower().startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="URL must start with http:// or https://")
    return url


MAX_HTML_SIZE = 10 * 1024 * 1024


async def _download_public_html(url: str) -> bytes:
    import httpx
    try:
        async with httpx.AsyncClient() as client:
            res = await client.get(
                url,
                timeout=15.0,
                follow_redirects=True,
                headers={
                    "User-Agent": "Mozilla/5.0 (compatible; AtlasLM/1.0; +https://atlaslm.app)",
                    "Accept": "text/html,application/xhtml+xml",
                },
            )
            res.raise_for_status()
            content_type = res.headers.get("content-type", "")
            if "text/html" not in content_type and "xml" not in content_type and content_type:
                raise HTTPException(
                    status_code=422,
                    detail="The URL did not return a web page. Only HTML pages are supported for now.",
                )
            return res.text.encode("utf-8")[:MAX_HTML_SIZE]
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(
            status_code=400,
            detail="AtlasLM could not reach that URL. Check the address and try again.",
        )


async def _youtube_ingest_payload(url: str, language: Optional[str]) -> Dict[str, Any]:
    try:
        transcription_language = normalize_transcription_language(language)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    try:
        result = await extract_youtube_transcript(url, language=transcription_language)
    except YouTubeExtractError as primary_error:
        try:
            blocks = await asyncio.to_thread(
                load_youtube,
                url,
                transcription_language,
            )
            transcript_text = _blocks_to_transcript_markdown(blocks)
            if not transcript_text:
                raise ValueError("No transcript text was produced.")
            video_id = extract_video_id(url) or "video"
            result = {
                "text": transcript_text,
                "title": f"YouTube {video_id}",
                "video_id": video_id,
                "language": transcription_language or "auto",
            }
        except Exception:
            raise HTTPException(
                status_code=422,
                detail=(
                    "AtlasLM could not extract or transcribe this YouTube video. "
                    "It may be private, blocked, or the backend media transcription "
                    f"tools may be unavailable. Caption error: {str(primary_error)}"
                ),
            )
    return {
        "filename": f"{result['title'][:200]} (YouTube)",
        "file_bytes": result["text"].encode("utf-8"),
        "canonical_url": f"https://www.youtube.com/watch?v={result['video_id']}",
        "language": transcription_language,
    }


def _format_seconds(seconds: float) -> str:
    total = max(0, int(seconds or 0))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def _blocks_to_transcript_markdown(blocks: List[Dict[str, Any]]) -> str:
    lines: List[str] = []
    for block in blocks:
        text = (block.get("text") or "").strip()
        if not text:
            continue
        timestamp = block.get("timestamp")
        if timestamp is not None:
            lines.append(f"## [{_format_seconds(float(timestamp))}]")
        lines.append(text)
        lines.append("")
    return "\n".join(lines).strip()


# -- Workspace Endpoints -------------------------------------------------------

@router.get("/workspaces", response_model=List[WorkspaceOut])
def list_workspaces(request: Request, db: Session = Depends(get_db)):
    """Return only workspaces owned by the authenticated user."""
    uid = current_user_id(request)
    return (
        db.query(Workspace)
        .filter(Workspace.user_id == uid)
        .order_by(Workspace.created_at.desc())
        .all()
    )


@router.post("/workspaces", response_model=WorkspaceOut, status_code=status.HTTP_201_CREATED)
def create_workspace(
    request: Request,
    workspace: WorkspaceCreate,
    db: Session = Depends(get_db),
):
    uid = current_user_id(request)
    db_workspace = Workspace(id=uuid.uuid4(), name=workspace.name, user_id=uid)
    db.add(db_workspace)
    db.commit()
    db.refresh(db_workspace)
    return db_workspace


@router.delete("/workspaces/{workspace_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_workspace(
    request: Request,
    workspace_id: uuid.UUID,
    db: Session = Depends(get_db),
):
    uid = current_user_id(request)
    # Fetch the workspace owned by this user or raise 404, then delete it.
    workspace = _get_owned_workspace(workspace_id, uid, db)
    db.delete(workspace)
    db.commit()
    return


# -- Document & Ingestion Endpoints -------------------------------------------

@router.get("/workspaces/{workspace_id}/documents", response_model=List[DocumentOut])
def list_documents(
    request: Request,
    workspace_id: uuid.UUID,
    db: Session = Depends(get_db),
):
    uid = current_user_id(request)
    _get_owned_workspace(workspace_id, uid, db)
    return (
        db.query(Document)
        .filter(Document.workspace_id == workspace_id)
        .order_by(Document.created_at.desc())
        .all()
    )


@router.get("/documents/{document_id}/status")
def get_document_status(
    request: Request,
    document_id: uuid.UUID,
    db: Session = Depends(get_db),
):
    """Poll ingestion status for a single document."""
    uid = current_user_id(request)
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    try:
        _get_owned_workspace(doc.workspace_id, uid, db)
    except HTTPException as exc:
        if exc.status_code == 404:
            raise HTTPException(status_code=404, detail="Document not found")
        raise
    return {
        "id": str(doc.id),
        "status": doc.status,
        "error_message": doc.error_message,
    }


@router.get("/documents/{document_id}/preview")
def preview_document(
    request: Request,
    document_id: uuid.UUID,
    db: Session = Depends(get_db),
):
    """Return a small, citable preview so users can verify what Atlas indexed."""
    uid = current_user_id(request)
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    _get_owned_workspace(doc.workspace_id, uid, db)
    chunks = (
        db.query(DocumentChunk)
        .filter(DocumentChunk.document_id == doc.id)
        .order_by(DocumentChunk.chunk_index.asc())
        .limit(12)
        .all()
    )
    return {
        "id": str(doc.id),
        "filename": doc.filename,
        "file_type": doc.file_type,
        "source_url": doc.source_url,
        "status": doc.status,
        "error_message": doc.error_message,
        "chunks": [
            {
                "id": str(chunk.id),
                "content": chunk.content,
                "page_number": chunk.page_number,
                "timestamp": chunk.timestamp,
                "sheet": chunk.sheet,
            }
            for chunk in chunks
        ],
    }


@router.post(
    "/workspaces/{workspace_id}/documents",
    response_model=DocumentOut,
    status_code=status.HTTP_201_CREATED,
)
async def upload_document(
    request: Request,
    workspace_id: uuid.UUID,
    file: UploadFile = File(...),
    language: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    uid = current_user_id(request)
    _get_owned_workspace(workspace_id, uid, db)
    idempotency_key = _request_idempotency_key(request)
    existing = _existing_idempotent_document(db, workspace_id, idempotency_key)
    if existing:
        return existing

    # Validate file size (50 MB limit)
    MAX_FILE_SIZE = 50 * 1024 * 1024
    file_bytes = await file.read()
    if len(file_bytes) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File size exceeds the maximum upload limit of 50MB.",
        )

    filename = file.filename or "uploaded-source"
    filename_lower = filename.lower()
    if filename_lower.endswith(".pdf"):
        file_type = "pdf"
    elif filename_lower.endswith(".md"):
        file_type = "md"
    elif filename_lower.endswith(".txt"):
        file_type = "txt"
    elif filename_lower.endswith(".docx"):
        file_type = "docx"
    elif filename_lower.endswith(".csv"):
        file_type = "csv"
    elif filename_lower.endswith(".xlsx"):
        file_type = "xlsx"
    elif filename_lower.endswith(".pptx"):
        file_type = "pptx"
    elif filename_lower.endswith((".png", ".jpg", ".jpeg", ".webp")):
        file_type = "image"
    elif filename_lower.endswith((".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac")):
        file_type = "audio"
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid file format. Supported: PDF, DOCX, XLSX, PPTX, TXT, MD, CSV, PNG, JPG, WEBP, MP3, WAV, M4A, AAC, OGG, FLAC.",
        )

    try:
        transcription_language = (
            normalize_transcription_language(language) if file_type == "audio" else None
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    pipeline = DocumentPipeline(db)

    # Async path: create placeholder doc, enqueue job, return 202.
    if redis_healthy():
        doc = pipeline.create_pending_document(
            workspace_id=workspace_id,
            filename=filename,
            file_type=file_type,
            idempotency_key=idempotency_key,
        )
        try:
            enqueue_ingestion_job(
                document_id=doc.id,
                workspace_id=workspace_id,
                filename=filename,
                file_type=file_type,
                file_bytes=file_bytes,
                language=transcription_language,
            )
        except Exception:
            # Queue push failed after doc creation - fall back to sync.
            db.delete(doc)
            db.commit()
        else:
            return JSONResponse(
                status_code=status.HTTP_202_ACCEPTED,
                content=jsonable_encoder(DocumentOut.model_validate(doc)),
            )

    # Sync fallback (Redis down): original behavior.
    try:
        doc = await pipeline.ingest_document(
            workspace_id=workspace_id,
            filename=filename,
            file_bytes=file_bytes,
            file_type=file_type,
            language=transcription_language,
            idempotency_key=idempotency_key,
        )
        return doc
    except ProviderError as e:
        raise HTTPException(status_code=503, detail=e.public_message)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post(
    "/workspaces/{workspace_id}/documents/url",
    response_model=DocumentOut,
    status_code=status.HTTP_201_CREATED,
)
async def ingest_url(
    request: Request,
    workspace_id: uuid.UUID,
    body: URLIngestRequest,
    db: Session = Depends(get_db),
):
    uid = current_user_id(request)
    _get_owned_workspace(workspace_id, uid, db)
    idempotency_key = _request_idempotency_key(request)
    existing = _existing_idempotent_document(db, workspace_id, idempotency_key)
    if existing:
        return existing

    url = _normalize_public_url(str(body.url))
    filename = url.replace("https://", "").replace("http://", "").split("/")[0] + " (Web)"
    html_bytes = await _download_public_html(url)

    pipeline = DocumentPipeline(db)

    # Async path (same pattern as upload_document)
    if redis_healthy():
        doc = pipeline.create_pending_document(
            workspace_id=workspace_id,
            filename=filename,
            file_type="url",
            source_url=url,
            idempotency_key=idempotency_key,
        )
        try:
            enqueue_ingestion_job(
                document_id=doc.id,
                workspace_id=workspace_id,
                filename=filename,
                file_type="url",
                file_bytes=html_bytes,
                source_url=url,
            )
        except Exception:
            db.delete(doc)
            db.commit()
        else:
            return JSONResponse(
                status_code=status.HTTP_202_ACCEPTED,
                content=jsonable_encoder(DocumentOut.model_validate(doc)),
            )

    # Sync fallback
    try:
        doc = await pipeline.ingest_document(
            workspace_id=workspace_id,
            filename=filename,
            file_bytes=html_bytes,
            file_type="url",
            source_url=url,
            idempotency_key=idempotency_key,
        )
        return doc
    except ProviderError as e:
        raise HTTPException(status_code=503, detail=e.public_message)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post(
    "/workspaces/{workspace_id}/documents/text",
    response_model=DocumentOut,
    status_code=status.HTTP_201_CREATED,
)
async def ingest_text(
    request: Request,
    workspace_id: uuid.UUID,
    body: TextIngestRequest,
    db: Session = Depends(get_db),
):
    uid = current_user_id(request)
    _get_owned_workspace(workspace_id, uid, db)
    idempotency_key = _request_idempotency_key(request)
    existing = _existing_idempotent_document(db, workspace_id, idempotency_key)
    if existing:
        return existing

    title = body.title.strip()
    content = body.content.strip()
    if not content:
        raise HTTPException(status_code=400, detail="Pasted text content cannot be empty.")

    MAX_TEXT_SIZE = 2 * 1024 * 1024
    file_bytes = content.encode("utf-8")
    if len(file_bytes) > MAX_TEXT_SIZE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Pasted text exceeds the maximum limit of 2MB.",
        )

    pipeline = DocumentPipeline(db)
    try:
        doc = await pipeline.ingest_document(
            workspace_id=workspace_id,
            filename=f"{title} (Pasted Text)",
            file_bytes=file_bytes,
            file_type="text",
            idempotency_key=idempotency_key,
        )
        return doc
    except ProviderError as e:
        raise HTTPException(status_code=503, detail=e.public_message)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(
    request: Request,
    document_id: uuid.UUID,
    db: Session = Depends(get_db),
):
    uid = current_user_id(request)
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    # Verify ownership via workspace, but do not leak workspace existence.
    try:
        _get_owned_workspace(doc.workspace_id, uid, db)
    except HTTPException as exc:
        if exc.status_code == 404:
            raise HTTPException(status_code=404, detail="Document not found")
        raise
    db.delete(doc)
    db.commit()
    return


class DocumentRetryRequest(BaseModel):
    language: Optional[str] = None


@router.post(
    "/documents/{document_id}/retry",
    response_model=DocumentOut,
)
async def retry_document(
    request: Request,
    document_id: uuid.UUID,
    db: Session = Depends(get_db),
    body: Optional[DocumentRetryRequest] = None,
):
    """Requeue the same authorized document. Never deletes the failed record."""
    uid = current_user_id(request)
    doc = _get_owned_document(document_id, uid, db)
    idempotency_key = _request_idempotency_key(request)
    previous_error = doc.error_message

    if doc.status in {"pending", "processing"}:
        return doc
    if doc.status == "ready":
        return doc

    kind = (doc.file_type or "").lower()
    if kind not in {"url", "youtube"} or not doc.source_url:
        raise HTTPException(
            status_code=422,
            detail="Re-add this file to retry. AtlasLM does not keep the original upload for retry.",
        )

    if idempotency_key:
        doc.idempotency_key = idempotency_key

    language = body.language if body else None
    try:
        if kind == "youtube":
            payload = await _youtube_ingest_payload(doc.source_url, language)
            filename = payload["filename"]
            file_bytes = payload["file_bytes"]
            source_url = payload["canonical_url"]
            transcription_language = payload["language"]
            doc.filename = filename
            doc.source_url = source_url
        else:
            file_bytes = await _download_public_html(doc.source_url)
            filename = doc.filename
            source_url = doc.source_url
            transcription_language = None
    except HTTPException as exc:
        doc.status = "failed"
        doc.error_message = str(exc.detail) if exc.detail else previous_error
        db.commit()
        db.refresh(doc)
        raise

    doc.status = "processing"
    db.commit()
    db.refresh(doc)

    pipeline = DocumentPipeline(db)
    if redis_healthy():
        try:
            enqueue_ingestion_job(
                document_id=doc.id,
                workspace_id=doc.workspace_id,
                filename=filename,
                file_type=doc.file_type,
                file_bytes=file_bytes,
                source_url=source_url,
                language=transcription_language,
            )
            return JSONResponse(
                status_code=status.HTTP_202_ACCEPTED,
                content=jsonable_encoder(DocumentOut.model_validate(doc)),
            )
        except Exception:
            pass

    try:
        await pipeline.run_ingestion_for_document(
            doc,
            file_bytes,
            doc.file_type,
            language=transcription_language,
        )
        doc.status = "ready"
        doc.error_message = None
        db.commit()
        db.refresh(doc)
        return doc
    except Exception as exc:
        doc.status = "failed"
        doc.error_message = previous_error or str(exc)
        db.commit()
        db.refresh(doc)
        raise HTTPException(
            status_code=400,
            detail=doc.error_message or "Atlas could not retry that source. The original record is unchanged.",
        )


# -- Chat Session Endpoints ----------------------------------------------------

@router.get("/workspaces/{workspace_id}/sessions", response_model=List[ChatSessionOut])
def list_sessions(
    request: Request,
    workspace_id: uuid.UUID,
    db: Session = Depends(get_db),
):
    uid = current_user_id(request)
    _get_owned_workspace(workspace_id, uid, db)
    return (
        db.query(ChatSession)
        .filter(ChatSession.workspace_id == workspace_id)
        .order_by(ChatSession.created_at.desc())
        .all()
    )


@router.post("/workspaces/{workspace_id}/sessions", response_model=ChatSessionOut)
def create_session(
    request: Request,
    workspace_id: uuid.UUID,
    session: ChatSessionCreate,
    db: Session = Depends(get_db),
):
    uid = current_user_id(request)
    _get_owned_workspace(workspace_id, uid, db)

    db_session = ChatSession(
        id=uuid.uuid4(),
        workspace_id=workspace_id,
        title=session.title or "New Chat",
        user_id=uid,
    )
    db.add(db_session)
    db.commit()
    db.refresh(db_session)
    return db_session


@router.get("/sessions/{session_id}", response_model=ChatSessionDetailsOut)
def get_session_details(
    request: Request,
    session_id: uuid.UUID,
    db: Session = Depends(get_db),
):
    uid = current_user_id(request)
    session = _get_owned_session(session_id, uid, db)
    return session


@router.delete("/sessions/{session_id}/messages", status_code=status.HTTP_204_NO_CONTENT)
def clear_session_messages(
    request: Request,
    session_id: uuid.UUID,
    db: Session = Depends(get_db),
):
    uid = current_user_id(request)
    session = _get_owned_session(session_id, uid, db)
    db.query(ChatMessage).filter(ChatMessage.session_id == session.id).delete()
    db.commit()
    return


# -- Streaming RAG Chat Endpoint -----------------------------------------------

@router.post("/sessions/{session_id}/chat/stream")
async def chat_stream(
    request: Request,
    session_id: uuid.UUID,
    message: ChatMessageCreate,
    db: Session = Depends(get_db),
):
    uid = current_user_id(request)
    session = db.query(ChatSession).filter(ChatSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Chat session not found")
    # Verify ownership via the owning workspace but do not leak workspace existence.
    try:
        ws = _get_owned_workspace(session.workspace_id, uid, db)
    except HTTPException as exc:
        if exc.status_code == 404:
            raise HTTPException(status_code=404, detail="Chat session not found")
        raise

    scope = scoped_document_ids(db, ws, message.synthesis_node_id)

    if settings.ATLAS_CHAT_RUNTIME == "mastra":
        run = create_run(
            db,
            user_id=uid,
            workspace_id=session.workspace_id,
            agent_id="notebook-research-agent",
            workflow_id="grounded-answer-workflow",
            runtime="mastra",
            request_id=request.headers.get("X-Request-ID"),
            idempotency_key=None,
            metadata={"session_id": str(session_id), "mode": message.mode},
        )
        run_context = {
            "run_id": run.id,
            "user_id": run.user_id,
            "workspace_id": run.workspace_id,
            "notebook_id": run.notebook_id,
            "request_id": run.request_id,
            "trace_id": run.trace_id,
        }
        append_run_event(db, run, "dispatch", "running", 15, "Sending the grounded question to Mastra")

        async def proxy():
            try:
                async for chunk in stream_mastra_chat(
                    **run_context,
                    session_id=session_id,
                    question=message.content,
                    source_ids=scope,
                    mode=message.mode,
                ):
                    yield chunk
                completed_run = db.query(AIRun).filter(AIRun.id == run_context["run_id"]).first()
                if completed_run:
                    completed_run.status = "completed"
                    completed_run.latency_ms = 0
                    db.commit()
                    append_run_event(db, completed_run, "saved", "completed", 100, "Conversation saved")
            except AIRuntimeError as exc:
                db.rollback()
                failed_run = db.query(AIRun).filter(AIRun.id == run_context["run_id"]).first()
                if failed_run:
                    failed_run.status = "failed"
                    failed_run.error_code = exc.code
                    failed_run.error_message = str(exc)
                    db.commit()
                    append_run_event(db, failed_run, "failed", "failed", 100, str(exc), {"error_code": exc.code})
                yield f"event: error\ndata: {json.dumps({'error': str(exc)})}\n\n".encode("utf-8")

        return StreamingResponse(proxy(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    rag = RAGService(db)
    return StreamingResponse(
        rag.execute_rag_chat_stream(
            workspace_id=session.workspace_id,
            session_id=session_id,
            user_message=message.content,
            answer_mode=message.mode,
            scope_doc_ids=scope,
        ),
        media_type="text/event-stream",
    )


# -- Contact / Captcha ---------------------------------------------------------

@router.post("/contact")
async def verify_contact(
    name: str = Form(...),
    email: str = Form(...),
    message: str = Form(...),
    captcha_answer: int = Form(...),
    captcha_expected: int = Form(...),
):
    """Mathematical captcha check."""
    if captcha_answer != captcha_expected:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Incorrect Captcha answer. Please try again.",
        )
    return {"status": "success", "message": "Thank you! Your message has been received."}


# -- Settings ------------------------------------------------------------------

@router.get("/settings/providers")
def get_available_providers():
    """Returns AtlasLM engine availability. Internal provider names are never exposed."""
    cloud_active = bool(
        settings.LANGDOCK_API_KEY
        or settings.LANGDOCK_API_CODE
        or settings.OPENROUTER_API_KEY
        or settings.OPENAI_API_KEY
        or settings.BLACKBOX_API_KEY
    )
    return {
        "providers": [
            {"id": "atlas-cloud", "name": "AtlasLM Cloud Engine",
             "status": "active" if cloud_active else "inactive"},
            {"id": "atlas-local", "name": "AtlasLM Local Engine",
             "status": "active"},
        ]
    }


# -- AtlasLM Studio Endpoints ------------------------------------------------

@router.get("/studio/types")
def list_studio_types():
    """Studio capabilities the dashboard may render.

    Only enabled types may be started from the UI. Disabled entries stay
    visible as planned so the dashboard never pretends an unfinished
    generator is live.
    """
    planned = "This Studio tool will be enabled after the notebook-to-report review."
    return {
        "types": [
            {
                "id": "report",
                "label": "Report",
                "detail": "Citation-backed report from ready sources",
                "enabled": True,
            },
            {
                "id": "study_guide",
                "label": "Study Guide",
                "detail": planned,
                "enabled": False,
                "reason": planned,
            },
            {
                "id": "mind_map",
                "label": "Mind Map",
                "detail": planned,
                "enabled": False,
                "reason": planned,
            },
            {
                "id": "quiz",
                "label": "Quiz",
                "detail": planned,
                "enabled": False,
                "reason": planned,
            },
            {
                "id": "flashcards",
                "label": "Flashcards",
                "detail": planned,
                "enabled": False,
                "reason": planned,
            },
            {
                "id": "audio_overview",
                "label": "Audio Overview",
                "detail": planned,
                "enabled": False,
                "reason": planned,
            },
        ]
    }



@router.post("/workspaces/{workspace_id}/studio", response_model=StudioOutputOut, status_code=201)
async def create_studio_output(
    request: Request,
    workspace_id: uuid.UUID,
    payload: StudioOutputCreate,
    db: Session = Depends(get_db),
):
    uid = current_user_id(request)
    ws = _get_owned_workspace(workspace_id, uid, db)

    # Report is the first durable Atlas workflow. It gets its own run record,
    # event stream, idempotency handling, and optional Mastra runtime while
    # retaining the existing Studio endpoint for backwards compatibility.
    if payload.output_type == "report":
        if payload.idempotency_key:
            existing_output = db.query(StudioOutput).filter(
                StudioOutput.workspace_id == ws.id,
                StudioOutput.output_type == "report",
                StudioOutput.idempotency_key == payload.idempotency_key,
            ).first()
            if existing_output:
                return _serialize_studio(db, existing_output)

        scope = payload.source_ids
        if scope is None:
            scope = scoped_document_ids(db, ws, payload.synthesis_node_id)
        if scope is not None:
            scoped_rows = db.query(Document).filter(
                Document.workspace_id == ws.id,
                Document.id.in_(scope),
            ).all() if scope else []
            if len(scoped_rows) != len(set(scope)):
                raise HTTPException(status_code=403, detail="One or more report sources are not in this notebook.")
            not_ready = [row.filename for row in scoped_rows if row.status != "ready"]
            if not_ready:
                raise HTTPException(
                    status_code=409,
                    detail=f"These sources are not ready yet: {', '.join(not_ready[:3])}",
                )

        runtime = settings.ATLAS_REPORT_RUNTIME if settings.ATLAS_REPORT_RUNTIME in {"legacy", "mastra"} else "legacy"
        trace_id = request_trace_id(request.headers.get("X-Request-ID"))
        run = create_run(
            db,
            user_id=uid,
            workspace_id=ws.id,
            agent_id="notebook-research-agent",
            workflow_id="report-workflow",
            runtime=runtime,
            request_id=request.headers.get("X-Request-ID"),
            idempotency_key=payload.idempotency_key,
            metadata={"output_type": "report", "length": payload.length, "focus": payload.focus},
        )
        output = StudioOutput(
            id=uuid.uuid4(),
            workspace_id=ws.id,
            synthesis_node_id=payload.synthesis_node_id,
            output_type="report",
            title=payload.title or _default_studio_title("report"),
            status="pending",
            run_id=run.id,
            runtime=runtime,
            source_scope=[str(source_id) for source_id in scope] if scope else None,
            idempotency_key=payload.idempotency_key,
            progress=0,
        )
        db.add(output)
        db.commit()
        db.refresh(output)
        try:
            if runtime == "mastra":
                append_run_event(db, run, "dispatch", "running", 15, "Sending the report workflow to Mastra")
                result = await call_mastra_report(
                    run=run,
                    output=output,
                    request_id=request.headers.get("X-Request-ID"),
                    source_ids=scope,
                    focus=payload.focus,
                    length=payload.length,
                )
                db.refresh(output)
                if result.get("status") == "ready":
                    run.status = "completed"
                    append_run_event(db, run, "saved", "completed", 100, "Mastra report saved")
                else:
                    run.status = "failed"
                    run.error_code = "mastra_report_failed"
                    run.error_message = result.get("error") or "Mastra could not finish the report."
                    db.commit()
            else:
                await generate_legacy_report(
                    db,
                    run,
                    output,
                    scope,
                    payload.focus,
                    payload.length,
                )
        except AIRuntimeError as exc:
            db.rollback()
            output = db.query(StudioOutput).filter(StudioOutput.id == output.id).first()
            run = db.query(AIRun).filter(AIRun.id == run.id).first()
            if output:
                output.status = "failed"
                output.error = str(exc)
                output.progress = 100
                output.retry_count = (output.retry_count or 0) + 1
                db.commit()
            if run:
                run.status = "failed"
                run.error_code = exc.code
                run.error_message = str(exc)
                db.commit()
                append_run_event(db, run, "failed", "failed", 100, str(exc), {"error_code": exc.code})
        except Exception:
            db.rollback()
            output = db.query(StudioOutput).filter(StudioOutput.id == output.id).first()
            run = db.query(AIRun).filter(AIRun.id == run.id).first()
            if output:
                output.status = "failed"
                output.error = "Atlas could not finish this report. Please try again."
                output.progress = 100
                output.retry_count = (output.retry_count or 0) + 1
                db.commit()
            if run:
                run.status = "failed"
                run.error_code = "unexpected_error"
                run.error_message = "Report generation failed."
                db.commit()
                append_run_event(db, run, "failed", "failed", 100, "Report generation failed.")
        return _serialize_studio(db, output)

    # Resolve scope with the EXISTING Patch 007 helper. A forged or cross-user
    # synthesis_node_id yields 404 here and can never widen scope.
    scope = scoped_document_ids(db, ws, payload.synthesis_node_id)  # None | [] | [ids]
    if scope is not None and len(scope) == 0:
        raise HTTPException(
            status_code=400,
            detail="No sources are wired into this synthesis node yet. "
                   "Connect one or more sources to it, then generate again.",
        )

    title = payload.title or _default_studio_title(payload.output_type)
    output = StudioOutput(
        id=uuid.uuid4(),
        workspace_id=ws.id,
        synthesis_node_id=payload.synthesis_node_id,
        output_type=payload.output_type,
        title=title,
        status="pending",
    )
    db.add(output)
    db.commit()
    db.refresh(output)

    # Generate inline so a missing or paused worker cannot leave the user with
    # a permanent "Building" card. These artifacts are intentionally small
    # and the API already has a 300 second execution budget in production.
    try:
        from ..services.rag import retrieve_chunks
        from ..services.studio_outputs import generate_studio_output

        chunks = retrieve_chunks(
            notebook_id=str(ws.id),
            query="key concepts, definitions, claims, facts, and main points across the sources",
            source_ids=[str(doc_id) for doc_id in scope] if scope is not None else [],
            k=24,
        )
        content, citations = generate_studio_output(payload.output_type, chunks)
        output.content = content
        output.status = "ready"
        output.error = None
        db.add_all([
            StudioOutputCitation(
                studio_output_id=output.id,
                document_id=uuid.UUID(citation["document_id"])
                if isinstance(citation["document_id"], str)
                else citation["document_id"],
                page_number=citation.get("page_number"),
            )
            for citation in citations
        ])
        db.commit()
        db.refresh(output)
    except Exception as exc:
        db.rollback()
        output = db.query(StudioOutput).filter_by(id=output.id).first()
        if output:
            output.status = "failed"
            output.error = str(exc) if isinstance(exc, (ValueError, ProviderError)) else "Atlas could not finish this output. Please try again."
            db.commit()

    return _serialize_studio(db, output)


@router.get("/workspaces/{workspace_id}/studio", response_model=list[StudioOutputOut])
def list_studio_outputs(
    request: Request,
    workspace_id: uuid.UUID,
    db: Session = Depends(get_db),
):
    uid = current_user_id(request)
    ws = _get_owned_workspace(workspace_id, uid, db)
    rows = (
        db.query(StudioOutput)
        .filter(StudioOutput.workspace_id == ws.id)
        .order_by(StudioOutput.created_at.desc())
        .all()
    )
    stale_cutoff = datetime.now(timezone.utc).timestamp() - (10 * 60)
    changed = False
    for row in rows:
        created_at = row.created_at
        if created_at is not None:
            if created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=timezone.utc)
            if (
                row.status in {"pending", "processing"}
                and created_at.timestamp() < stale_cutoff
            ):
                row.status = "failed"
                row.error = "This output did not finish. Generate it again to retry."
                changed = True
    if changed:
        db.commit()
    return [_serialize_studio(db, r) for r in rows]


@router.get("/workspaces/{workspace_id}/studio/{output_id}", response_model=StudioOutputOut)
def get_studio_output(
    request: Request,
    workspace_id: uuid.UUID,
    output_id: uuid.UUID,
    db: Session = Depends(get_db),
):
    uid = current_user_id(request)
    ws = _get_owned_workspace(workspace_id, uid, db)
    output = db.query(StudioOutput).filter_by(id=output_id, workspace_id=ws.id).first()
    if not output:
        raise HTTPException(status_code=404, detail="Studio output not found.")
    return _serialize_studio(db, output)


@router.delete("/workspaces/{workspace_id}/studio/{output_id}", status_code=204)
def delete_studio_output(
    request: Request,
    workspace_id: uuid.UUID,
    output_id: uuid.UUID,
    db: Session = Depends(get_db),
):
    uid = current_user_id(request)
    ws = _get_owned_workspace(workspace_id, uid, db)
    output = db.query(StudioOutput).filter_by(id=output_id, workspace_id=ws.id).first()
    if not output:
        raise HTTPException(status_code=404, detail="Studio output not found.")
    db.delete(output)
    db.commit()
    return None


# ---------- helpers ----------

def _default_studio_title(output_type: str) -> str:
    return {
        "report": "Atlas Research Report",
        "mind_map": "Mind Map",
        "study_guide": "Study Guide",
        "quiz": "Quiz",
        "flashcards": "Flashcards",
    }.get(output_type, "Studio Output")


def _serialize_studio(db, output):
    cites = (db.query(StudioOutputCitation, Document)
               .join(Document, StudioOutputCitation.document_id == Document.id)
               .filter(StudioOutputCitation.studio_output_id == output.id)
               .all())
    out = StudioOutputOut.model_validate(output)
    out.citations = [StudioCitationOut(
        document_id=citation.document_id,
        chunk_id=citation.chunk_id,
        page_number=citation.page_number,
        filename=document.filename,
        quote=citation.quote,
        source_url=citation.source_url or document.source_url,
    ) for citation, document in cites]
    return out


# ---- AI run and dashboard layout contracts ---------------------------------

DEFAULT_LAYOUT = {
    "source_panel_width": 320,
    "output_panel_width": 360,
    "source_panel_collapsed": False,
    "output_panel_collapsed": False,
}


@router.get("/workspaces/{workspace_id}/ai-runs", response_model=list[AIRunOut])
def list_ai_runs(
    request: Request,
    workspace_id: uuid.UUID,
    db: Session = Depends(get_db),
):
    uid = current_user_id(request)
    ws = _get_owned_workspace(workspace_id, uid, db)
    return db.query(AIRun).filter(
        AIRun.workspace_id == ws.id,
        AIRun.user_id == uid,
    ).order_by(AIRun.created_at.desc()).limit(50).all()


@router.get("/workspaces/{workspace_id}/ai-runs/{run_id}/events", response_model=list[AIRunEventOut])
def list_ai_run_events(
    request: Request,
    workspace_id: uuid.UUID,
    run_id: uuid.UUID,
    db: Session = Depends(get_db),
):
    uid = current_user_id(request)
    ws = _get_owned_workspace(workspace_id, uid, db)
    run = db.query(AIRun).filter(
        AIRun.id == run_id,
        AIRun.workspace_id == ws.id,
        AIRun.user_id == uid,
    ).first()
    if not run:
        raise HTTPException(status_code=404, detail="AI run not found")
    return db.query(AIRunEvent).filter(AIRunEvent.run_id == run.id).order_by(AIRunEvent.created_at.asc()).all()


def _safe_layout(value: dict[str, Any]) -> dict[str, Any]:
    """Only persist known layout fields and bounded panel dimensions."""
    result = dict(DEFAULT_LAYOUT)
    for key in ("source_panel_collapsed", "output_panel_collapsed"):
        if key in value:
            result[key] = bool(value[key])
    for key in ("source_panel_width", "output_panel_width"):
        if key in value:
            try:
                result[key] = max(240, min(520, int(value[key])))
            except (TypeError, ValueError):
                pass
    return result


@router.get("/workspaces/{workspace_id}/layout", response_model=WorkspaceLayoutOut)
def get_workspace_layout(
    request: Request,
    workspace_id: uuid.UUID,
    db: Session = Depends(get_db),
):
    uid = current_user_id(request)
    ws = _get_owned_workspace(workspace_id, uid, db)
    row = db.query(WorkspaceLayout).filter(
        WorkspaceLayout.workspace_id == ws.id,
        WorkspaceLayout.user_id == uid,
    ).first()
    if not row:
        return {
            "workspace_id": ws.id,
            "layout": DEFAULT_LAYOUT,
            "updated_at": ws.created_at,
        }
    return row


@router.put("/workspaces/{workspace_id}/layout", response_model=WorkspaceLayoutOut)
def save_workspace_layout(
    request: Request,
    workspace_id: uuid.UUID,
    payload: WorkspaceLayoutUpdate,
    db: Session = Depends(get_db),
):
    uid = current_user_id(request)
    ws = _get_owned_workspace(workspace_id, uid, db)
    row = db.query(WorkspaceLayout).filter(
        WorkspaceLayout.workspace_id == ws.id,
        WorkspaceLayout.user_id == uid,
    ).first()
    if not row:
        row = WorkspaceLayout(
            id=uuid.uuid4(),
            user_id=uid,
            workspace_id=ws.id,
            layout=_safe_layout(payload.layout),
        )
        db.add(row)
    else:
        row.layout = _safe_layout(payload.layout)
    db.commit()
    db.refresh(row)
    return row


@router.delete("/workspaces/{workspace_id}/layout", status_code=204)
def reset_workspace_layout(
    request: Request,
    workspace_id: uuid.UUID,
    db: Session = Depends(get_db),
):
    uid = current_user_id(request)
    ws = _get_owned_workspace(workspace_id, uid, db)
    row = db.query(WorkspaceLayout).filter(
        WorkspaceLayout.workspace_id == ws.id,
        WorkspaceLayout.user_id == uid,
    ).first()
    if row:
        db.delete(row)
        db.commit()
    return None


# ---- Deep Research schemas --------------------------------------------------
class ResearchSearchRequest(BaseModel):
    query: str
    web: bool = True
    academic: bool = True
    limit: int = 8


class ResearchIngestRequest(BaseModel):
    query: str
    results: List[dict]              # the picked ResearchResult dicts from search
    fetch_full_text: bool = True


# ---- POST /api/v1/workspaces/{workspace_id}/research/search ---------------
@router.post("/workspaces/{workspace_id}/research/search")
def research_search(
    workspace_id: uuid.UUID,
    body: ResearchSearchRequest,
    request: Request,
    db: Session = Depends(get_db)
):
    uid = current_user_id(request)
    _get_owned_workspace(workspace_id, uid, db)
    
    if not body.query.strip():
        raise HTTPException(400, "query is required")
        
    # enqueue for traceability (mirrors Studio queue pattern), run inline (fast)
    job_id = research_jobs.enqueue("search", {
        "workspace_id": str(workspace_id), "query": body.query,
        "web": body.web, "academic": body.academic,
    })
    try:
        results = _research.search(
            body.query, web=body.web, academic=body.academic, limit=body.limit)
        research_jobs.set_status(job_id, "done", {"count": len(results)})
    except Exception as e:                           # noqa: BLE001
        research_jobs.set_status(job_id, "error", {"error": "search failed"})
        raise HTTPException(502, "Deep Research search is temporarily unavailable")
    return {"job_id": job_id, "query": body.query, "results": results}


# ---- POST /api/v1/workspaces/{workspace_id}/research/ingest --------------
@router.post("/workspaces/{workspace_id}/research/ingest")
def research_ingest(
    workspace_id: uuid.UUID,
    body: ResearchIngestRequest,
    request: Request,
    db: Session = Depends(get_db)
):
    uid = current_user_id(request)
    _get_owned_workspace(workspace_id, uid, db)
    
    if not body.results:
        raise HTTPException(400, "no results selected")
        
    # heavy full-text fetch -> enqueue so the request returns immediately
    job_id = research_jobs.enqueue("ingest", {
        "workspace_id": str(workspace_id), "query": body.query,
        "results": body.results, "fetch_full_text": body.fetch_full_text,
    })
    return {"job_id": job_id, "status": "pending",
            "queued": len(body.results)}


# ---- GET /api/v1/research/jobs/{job_id} ----------------------------------
@router.get("/research/jobs/{job_id}")
def research_job_status(
    job_id: str,
    request: Request,
    db: Session = Depends(get_db)
):
    uid = current_user_id(request)
    job = research_jobs.get_job(job_id)
    if not job:
        raise HTTPException(404, "job not found")
        
    payload = job.get("payload")
    if payload and "workspace_id" in payload:
        try:
            ws_id = uuid.UUID(payload["workspace_id"])
            _get_owned_workspace(ws_id, uid, db)
        except Exception:
            raise HTTPException(status_code=404, detail="job not found")
            
    return job


# -- Helper for User Profiles --------------------------------------------------
def _get_or_create_profile(db: Session, user_id: str) -> UserProfile:
    profile = db.query(UserProfile).filter(UserProfile.user_id == user_id).first()
    if not profile:
        profile = UserProfile(user_id=user_id, tour_completed=False, marketing_opt_in=False)
        db.add(profile)
        db.commit()
        db.refresh(profile)
    return profile


# -- YouTube Ingestion Endpoint ------------------------------------------------
@router.post(
    "/workspaces/{workspace_id}/documents/youtube",
    response_model=DocumentOut,
    status_code=status.HTTP_201_CREATED,
)
async def ingest_youtube(
    request: Request,
    workspace_id: uuid.UUID,
    body: URLIngestRequest,
    db: Session = Depends(get_db),
):
    uid = current_user_id(request)
    _get_owned_workspace(workspace_id, uid, db)
    idempotency_key = _request_idempotency_key(request)
    existing = _existing_idempotent_document(db, workspace_id, idempotency_key)
    if existing:
        return existing

    url = _normalize_public_url(str(body.url))
    payload = await _youtube_ingest_payload(url, body.language)
    filename = payload["filename"]
    file_bytes = payload["file_bytes"]
    canonical_url = payload["canonical_url"]
    transcription_language = payload["language"]

    pipeline = DocumentPipeline(db)

    # Async path via Redis queue
    if redis_healthy():
        doc = pipeline.create_pending_document(
            workspace_id=workspace_id,
            filename=filename,
            file_type="youtube",
            source_url=canonical_url,
            idempotency_key=idempotency_key,
        )
        try:
            enqueue_ingestion_job(
                document_id=doc.id,
                workspace_id=workspace_id,
                filename=filename,
                file_type="youtube",
                file_bytes=file_bytes,
                source_url=canonical_url,
                language=transcription_language,
            )
        except Exception:
            db.delete(doc)
            db.commit()
        else:
            return JSONResponse(
                status_code=status.HTTP_202_ACCEPTED,
                content=jsonable_encoder(DocumentOut.model_validate(doc)),
            )

    # Sync fallback
    try:
        doc = await pipeline.ingest_document(
            workspace_id=workspace_id,
            filename=filename,
            file_bytes=file_bytes,
            file_type="youtube",
            source_url=canonical_url,
            language=transcription_language,
            idempotency_key=idempotency_key,
        )
        return doc
    except ProviderError as e:
        raise HTTPException(status_code=503, detail=e.public_message)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# -- Workspace Graph (Canvas Connections) Endpoints ----------------------------
@router.get("/workspaces/{workspace_id}/graph", response_model=list[GraphEdgeOut])
def list_graph_edges(workspace_id: uuid.UUID, request: Request, db: Session = Depends(get_db)):
    uid = current_user_id(request)
    ws = _get_owned_workspace(workspace_id, uid, db)
    return db.query(WorkspaceGraphEdge).filter(WorkspaceGraphEdge.workspace_id == ws.id).all()


@router.post("/workspaces/{workspace_id}/graph", response_model=GraphEdgeOut, status_code=201)
def create_graph_edge(workspace_id: uuid.UUID, payload: GraphEdgeCreate,
                      request: Request, db: Session = Depends(get_db)):
    uid = current_user_id(request)
    ws = _get_owned_workspace(workspace_id, uid, db)
    if payload.from_document_id == payload.to_document_id:
        raise HTTPException(status_code=400, detail="A source cannot connect to itself.")
    docs = db.query(Document).filter(
        Document.workspace_id == ws.id,
        Document.id.in_([payload.from_document_id, payload.to_document_id]),
    ).count()
    if docs != 2:
        raise HTTPException(status_code=404, detail="Source not found in this notebook.")
    existing = db.query(WorkspaceGraphEdge).filter_by(
        workspace_id=ws.id,
        from_document_id=payload.from_document_id,
        to_document_id=payload.to_document_id,
    ).first()
    if existing:
        return existing  # idempotent
    edge = WorkspaceGraphEdge(workspace_id=ws.id,
                              from_document_id=payload.from_document_id,
                              to_document_id=payload.to_document_id)
    db.add(edge); db.commit(); db.refresh(edge)
    return edge


@router.delete("/workspaces/{workspace_id}/graph/{edge_id}", status_code=204)
def delete_graph_edge(workspace_id: uuid.UUID, edge_id: uuid.UUID,
                      request: Request, db: Session = Depends(get_db)):
    uid = current_user_id(request)
    ws = _get_owned_workspace(workspace_id, uid, db)
    edge = db.query(WorkspaceGraphEdge).filter_by(id=edge_id, workspace_id=ws.id).first()
    if not edge:
        raise HTTPException(status_code=404, detail="Connection not found.")
    db.delete(edge); db.commit()


# -- Canvas Node Positions Endpoints -------------------------------------------
@router.put("/workspaces/{workspace_id}/graph/positions", status_code=204)
def save_node_positions(workspace_id: uuid.UUID, payload: list[NodePositionUpdate],
                        request: Request, db: Session = Depends(get_db)):
    uid = current_user_id(request)
    ws = _get_owned_workspace(workspace_id, uid, db)
    doc_ids = {d.id for d in db.query(Document.id).filter(Document.workspace_id == ws.id).all()}
    for item in payload:
        if item.document_id not in doc_ids:
            continue
        pos = db.query(CanvasPosition).filter_by(document_id=item.document_id).first()
        if pos is None:
            pos = CanvasPosition(document_id=item.document_id, workspace_id=ws.id)
            db.add(pos)
        pos.x_pos, pos.y_pos = item.x_pos, item.y_pos
    db.commit()


@router.get("/workspaces/{workspace_id}/graph/positions")
def get_node_positions(workspace_id: uuid.UUID, request: Request, db: Session = Depends(get_db)):
    uid = current_user_id(request)
    ws = _get_owned_workspace(workspace_id, uid, db)
    rows = db.query(CanvasPosition).filter(CanvasPosition.workspace_id == ws.id).all()
    return [{"document_id": str(r.document_id), "x_pos": r.x_pos, "y_pos": r.y_pos} for r in rows]


# -- Onboarding Flags Endpoints ------------------------------------------------
@router.get("/me/onboarding", response_model=OnboardingFlagsOut)
def get_onboarding_flags(request: Request, db: Session = Depends(get_db)):
    uid = current_user_id(request)
    profile = _get_or_create_profile(db, uid)
    return OnboardingFlagsOut(tour_completed=profile.tour_completed,
                              marketing_opt_in=profile.marketing_opt_in)


@router.patch("/me/onboarding", response_model=OnboardingFlagsOut)
def update_onboarding_flags(payload: OnboardingFlagsUpdate,
                            request: Request, db: Session = Depends(get_db)):
    uid = current_user_id(request)
    profile = _get_or_create_profile(db, uid)
    if payload.tour_completed is not None:
        profile.tour_completed = payload.tour_completed
    if payload.marketing_opt_in is not None:
        profile.marketing_opt_in = payload.marketing_opt_in
    db.commit(); db.refresh(profile)
    return OnboardingFlagsOut(tour_completed=profile.tour_completed,
                              marketing_opt_in=profile.marketing_opt_in)


# -- Synthesis Endpoints -------------------------------------------------------

@router.get("/workspaces/{workspace_id}/synthesis", response_model=list[SynthesisNodeOut])
def list_synthesis_nodes(workspace_id: uuid.UUID, request: Request, db: Session = Depends(get_db)):
    uid = current_user_id(request)
    ws = _get_owned_workspace(workspace_id, uid, db)  # 404 if not owner
    nodes = db.query(SynthesisNode).filter(SynthesisNode.workspace_id == ws.id).all()
    return [_serialize_synthesis(db, n) for n in nodes]


@router.post("/workspaces/{workspace_id}/synthesis", response_model=SynthesisNodeOut, status_code=201)
def create_synthesis_node(workspace_id: uuid.UUID, payload: SynthesisNodeCreate,
                          request: Request, db: Session = Depends(get_db)):
    uid = current_user_id(request)
    ws = _get_owned_workspace(workspace_id, uid, db)
    node = SynthesisNode(workspace_id=ws.id, title=payload.title or "Synthesis",
                         x_pos=payload.x_pos, y_pos=payload.y_pos)
    db.add(node); db.commit(); db.refresh(node)
    return _serialize_synthesis(db, node)


@router.patch("/workspaces/{workspace_id}/synthesis/{node_id}", response_model=SynthesisNodeOut)
def update_synthesis_node(workspace_id: uuid.UUID, node_id: uuid.UUID, payload: SynthesisNodeUpdate,
                          request: Request, db: Session = Depends(get_db)):
    uid = current_user_id(request)
    ws = _get_owned_workspace(workspace_id, uid, db)
    node = _get_owned_synthesis(db, ws, node_id)  # 404 if not in this workspace
    if payload.title is not None: node.title = payload.title
    if payload.x_pos is not None: node.x_pos = payload.x_pos
    if payload.y_pos is not None: node.y_pos = payload.y_pos
    db.commit(); db.refresh(node)
    return _serialize_synthesis(db, node)


@router.delete("/workspaces/{workspace_id}/synthesis/{node_id}", status_code=204)
def delete_synthesis_node(workspace_id: uuid.UUID, node_id: uuid.UUID,
                          request: Request, db: Session = Depends(get_db)):
    uid = current_user_id(request)
    ws = _get_owned_workspace(workspace_id, uid, db)
    node = _get_owned_synthesis(db, ws, node_id)
    db.delete(node); db.commit()  # inputs cascade-delete


@router.post("/workspaces/{workspace_id}/synthesis/{node_id}/inputs", status_code=201)
def add_synthesis_input(workspace_id: uuid.UUID, node_id: uuid.UUID, payload: SynthesisInputCreate,
                        request: Request, db: Session = Depends(get_db)):
    uid = current_user_id(request)
    ws = _get_owned_workspace(workspace_id, uid, db)
    node = _get_owned_synthesis(db, ws, node_id)
    # The document must belong to the same workspace. Never wire across notebooks.
    doc = db.query(Document).filter_by(id=payload.document_id, workspace_id=ws.id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Source not found in this notebook.")
    existing = db.query(SynthesisInput).filter_by(
        synthesis_node_id=node.id, document_id=doc.id).first()
    if existing:
        return  # idempotent
    db.add(SynthesisInput(synthesis_node_id=node.id, document_id=doc.id))
    db.commit()


@router.delete("/workspaces/{workspace_id}/synthesis/{node_id}/inputs/{document_id}", status_code=204)
def remove_synthesis_input(workspace_id: uuid.UUID, node_id: uuid.UUID, document_id: uuid.UUID,
                           request: Request, db: Session = Depends(get_db)):
    uid = current_user_id(request)
    ws = _get_owned_workspace(workspace_id, uid, db)
    node = _get_owned_synthesis(db, ws, node_id)
    link = db.query(SynthesisInput).filter_by(
        synthesis_node_id=node.id, document_id=document_id).first()
    if not link:
        raise HTTPException(status_code=404, detail="Connection not found.")
    db.delete(link); db.commit()


# -- Private Helpers for Synthesis ---------------------------------------------

def _get_owned_synthesis(db: Session, ws: Workspace, node_id: uuid.UUID) -> SynthesisNode:
    node = db.query(SynthesisNode).filter_by(id=node_id, workspace_id=ws.id).first()
    if not node:
        raise HTTPException(status_code=404, detail="Synthesis node not found.")
    return node


def _serialize_synthesis(db: Session, node: SynthesisNode) -> SynthesisNodeOut:
    ids = [r.document_id for r in
           db.query(SynthesisInput).filter_by(synthesis_node_id=node.id).all()]
    out = SynthesisNodeOut.model_validate(node)
    out.input_document_ids = ids
    return out


def scoped_document_ids(db: Session, ws: Workspace, synthesis_node_id: uuid.UUID | None) -> list[uuid.UUID] | None:
    if synthesis_node_id is None:
        return None
    node = _get_owned_synthesis(db, ws, synthesis_node_id)
    ids = [r.document_id for r in
           db.query(SynthesisInput).filter_by(synthesis_node_id=node.id).all()]
    return ids


# ============================================================================
# PATCH 010 - Studio Finish: Audio Overview + Export + Share routes
# ============================================================================

import os
from typing import List, Optional
from pydantic import BaseModel
from fastapi import Depends, HTTPException
from fastapi.responses import Response, FileResponse

from app.services.audio.service import AudioOverviewService
from app.services.audio import export as audio_export
from app.services.audio import share as audio_share

class RealRetriever:
    def retrieve(self, db, workspace_id, doc_ids=None):
        from app.services.rag import retrieve_chunks
        return retrieve_chunks(
            notebook_id=str(workspace_id),
            query="key concepts, central topics, and main points across the sources",
            source_ids=[str(d) for d in doc_ids] if doc_ids else [],
            k=24
        )

class RealGenerator:
    def complete(self, prompt, context_chunks=None):
        from app.services.rag import call_model, RAGService
        system_prompt, _ = RAGService(None).construct_system_prompt([])
        context = ""
        if context_chunks:
            context = "\n\n".join(
                f"[S{i+1}] (doc:{c['document_id']} p{c.get('page_number', 1)})\n{c['text']}"
                for i, c in enumerate(context_chunks)
            )
        user_prompt = f"{prompt}\n\nSOURCES:\n{context}"
        return call_model(system=system_prompt, user=user_prompt)

_gen = RealGenerator()
_ret = RealRetriever()
_audio = AudioOverviewService(generation_client=_gen, retriever=_ret)


class AudioGenerateRequest(BaseModel):
    title: str
    style: str = "deep_dive"          # "deep_dive" | "brief"
    voice: str = "atlas-offline"       # free, on-device default
    doc_ids: Optional[List[str]] = None


# ---- POST /workspaces/{workspace_id}/audio/generate -----------------------
@router.post("/workspaces/{workspace_id}/audio/generate")
def audio_generate(workspace_id: uuid.UUID, body: AudioGenerateRequest,
                   request: Request, db: Session = Depends(get_db)):
    uid = current_user_id(request)
    _get_owned_workspace(workspace_id, uid, db)
    if not body.title.strip():
        raise HTTPException(400, "title is required")
    ready_query = db.query(Document).filter(
        Document.workspace_id == workspace_id,
        Document.status == "ready",
    )
    if body.doc_ids:
        ready_query = ready_query.filter(Document.id.in_(body.doc_ids))
    if ready_query.count() == 0:
        raise HTTPException(
            status_code=400,
            detail="Add at least one ready source before generating an audio overview.",
        )
    try:
        ov = _audio.generate(
            db, str(workspace_id), title=body.title, style=body.style,
            voice=body.voice, doc_ids=body.doc_ids,
        )
    except ProviderError as e:
        raise HTTPException(status_code=503, detail=e.public_message)
    except Exception:
        raise HTTPException(
            status_code=500,
            detail="AtlasLM could not generate the audio overview. Please try again.",
        )
    db.commit()
    return {
        "overview_id": ov.overview_id,
        "title": ov.title,
        "duration": ov.duration,
        "voice": ov.voice,
        "style": ov.style,
        "transcript": ov.transcript(),
        "audio_url": f"/api/v1/workspaces/{workspace_id}/audio/{ov.overview_id}/stream",
    }


# ---- GET .../audio/{overview_id}/stream  (authed playback) ----------------
@router.get("/workspaces/{workspace_id}/audio/{overview_id}/stream")
def audio_stream(workspace_id: uuid.UUID, overview_id: str,
                 request: Request, db: Session = Depends(get_db)):
    uid = current_user_id(request)
    _get_owned_workspace(workspace_id, uid, db)
    row = _audio.get(db, overview_id)
    if not row or row.workspace_id != str(workspace_id):
        raise HTTPException(404, "overview not found")
    if not os.path.exists(row.audio_path):
        raise HTTPException(404, "audio not available")
    return FileResponse(row.audio_path, media_type="audio/wav")


# ---- GET .../audio/{overview_id}/export?format=pdf|md ---------------------
@router.get("/workspaces/{workspace_id}/audio/{overview_id}/export")
def audio_export_route(workspace_id: uuid.UUID, overview_id: str, request: Request,
                       format: str = "pdf", db: Session = Depends(get_db)):
    uid = current_user_id(request)
    _get_owned_workspace(workspace_id, uid, db)
    row = _audio.get(db, overview_id)
    if not row or row.workspace_id != str(workspace_id):
        raise HTTPException(404, "overview not found")
    lines = row.transcript
    
    # We can retrieve the workspace documents to populate the sources list!
    docs = db.query(Document).filter(Document.workspace_id == workspace_id).all()
    # Map them to a list of dicts that can be indexed
    doc_map = {str(d.id): d for d in docs}
    
    # To be simple and robust: build the sources list from the chunks list order!
    chunks = _ret.retrieve(db, workspace_id, doc_ids=[str(d.id) for d in docs])
    seen = {}
    for c in chunks:
        seen.setdefault(c["document_id"], len(seen) + 1)
    
    sources = [
        {
            "name": doc_map[d].filename if d in doc_map else "Source",
            "source_label": doc_map[d].source_label if d in doc_map else None,
            "external_url": doc_map[d].external_url if d in doc_map else None,
        }
        for d in seen.keys()
    ]
    
    if format == "md":
        md = audio_export.to_markdown(row.title, lines, sources=sources)
        return Response(md, media_type="text/markdown", headers={
            "Content-Disposition": f'attachment; filename="{overview_id}.md"'})
    if format == "pdf":
        pdf = audio_export.to_pdf(row.title, lines, sources=sources)
        return Response(pdf, media_type="application/pdf", headers={
            "Content-Disposition": f'attachment; filename="{overview_id}.pdf"'})
    raise HTTPException(400, "format must be pdf or md")


# ---- POST/DELETE .../audio/{overview_id}/share  (create / revoke link) ----
@router.post("/workspaces/{workspace_id}/audio/{overview_id}/share")
def audio_share_create(workspace_id: uuid.UUID, overview_id: str,
                       request: Request, db: Session = Depends(get_db)):
    uid = current_user_id(request)
    _get_owned_workspace(workspace_id, uid, db)
    row = _audio.get(db, overview_id)
    if not row or row.workspace_id != str(workspace_id):
        raise HTTPException(404, "overview not found")
    token = audio_share.enable(db, overview_id)
    db.commit()
    return {"share_url": f"/listen/{token}", "token": token}


@router.delete("/workspaces/{workspace_id}/audio/{overview_id}/share")
def audio_share_revoke(workspace_id: uuid.UUID, overview_id: str,
                       request: Request, db: Session = Depends(get_db)):
    uid = current_user_id(request)
    _get_owned_workspace(workspace_id, uid, db)
    row = _audio.get(db, overview_id)
    if not row or row.workspace_id != str(workspace_id):
        raise HTTPException(404, "overview not found")
    audio_share.disable(db, overview_id)
    db.commit()
    return {"ok": True}


# ---- PUBLIC (no auth) read-only listen page data + stream -----------------
@router.get("/public/audio/{token}")
def public_audio(token: str, db: Session = Depends(get_db)):
    data = audio_share.get_public(db, token)
    if not data:
        raise HTTPException(404, "link not found")
    return data


@router.get("/public/audio/{token}/stream")
def public_audio_stream(token: str, db: Session = Depends(get_db)):
    from app.models import AudioOverviewRow
    row = (db.query(AudioOverviewRow)
             .filter(AudioOverviewRow.share_token == token,
                     AudioOverviewRow.is_public.is_(True)).first())
    if not row or not os.path.exists(row.audio_path):
        raise HTTPException(404, "link not found")
    return FileResponse(row.audio_path, media_type="audio/wav")


# ============================================================================
# PATCH 011 - Google Workspace connector routes
# APPEND the contents of this file at the BOTTOM of your EXISTING
# backend/app/api/endpoints.py (the consolidated api/v1 router). Do NOT create a
# new router file - reuse the same `router`, `get_current_user`, and the DB
# session dependency the other routes use.
# ============================================================================
import os
import json
import time
import secrets
import logging
from typing import List, Optional
from pydantic import BaseModel
from fastapi import Depends, HTTPException
from fastapi.responses import RedirectResponse

from app.auth import get_current_user
from app.core.database import get_db
from app.services.connections.oauth import GoogleOAuth
from app.services.connections.drive import DriveConnector
from app.services.connections.manager import ConnectionManager

_log = logging.getLogger("api.connections")
_FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")

# Short-lived CSRF/PKCE state. Swap for Redis in multi-instance deploys; the
# interface (set/pop) is intentionally tiny so that is a drop-in change.
_PENDING: dict = {}
_STATE_TTL = 600


def _state_set(state: str, payload: dict) -> None:
    _PENDING[state] = (time.time() + _STATE_TTL, payload)
    for k in [k for k, (exp, _) in _PENDING.items() if exp < time.time()]:
        _PENDING.pop(k, None)


def _state_pop(state: str) -> Optional[dict]:
    item = _PENDING.pop(state, None)
    if not item or item[0] < time.time():
        return None
    return item[1]


# ---- persist bridge: route picked Drive files into the EXISTING pipeline ----
def _persist_drive_file(workspace_id: str, filename: str, ext: str, raw: bytes, db: Session):
    """Write bytes to a temp file and run the EXISTING Patch-003 ingest path."""
    import tempfile
    from app.services.ingest.dispatcher import detect_kind, extract_blocks
    with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
        tmp.write(raw)
        path = tmp.name
    try:
        kind = detect_kind(path)
        blocks = extract_blocks(kind, path)
        from app.services.rag import persist_blocks
        source_id = persist_blocks(workspace_id, filename, kind, blocks, origin="google_drive")
        return source_id, len(blocks)
    finally:
        try: os.unlink(path)
        except OSError: pass


# ---- POST /api/v1/connections/google/start --------------------------------
@router.post("/connections/google/start")
def google_start(workspace_id: str, user=Depends(get_current_user)):
    oauth = GoogleOAuth()
    if not oauth.configured:
        raise HTTPException(503, "Google connector is not configured on this server.")
    state = secrets.token_urlsafe(24)
    auth_url, verifier = oauth.build_auth_url(state)
    _state_set(state, {"user_id": str(user.id), "workspace_id": workspace_id,
                       "verifier": verifier})
    return {"auth_url": auth_url}


# ---- GET /api/v1/connections/google/callback ------------------------------
@router.get("/connections/google/callback")
def google_callback(state: str = "", code: str = "", error: str = "",
                    db=Depends(get_db)):
    ctx = _state_pop(state)
    if error or not ctx or not code:
        return RedirectResponse(f"{_FRONTEND_URL}/settings/connections?google=error")
    try:
        oauth = GoogleOAuth()
        tokens = oauth.exchange_code(code, ctx["verifier"])
        ConnectionManager(db).save(user_id=ctx["user_id"],
                                   workspace_id=ctx["workspace_id"], tokens=tokens)
    except Exception as e:
        _log.warning("google callback failed: %s", e)
        return RedirectResponse(f"{_FRONTEND_URL}/settings/connections?google=error")
    return RedirectResponse(f"{_FRONTEND_URL}/settings/connections?google=connected")


# ---- GET /api/v1/connections/google ---------------------------------------
@router.get("/connections/google")
def google_status(workspace_id: str, user=Depends(get_current_user),
                  db=Depends(get_db)):
    return ConnectionManager(db).status(workspace_id=workspace_id)


# ---- GET /api/v1/connections/google/picker-config -------------------------
@router.get("/connections/google/picker-config")
def google_picker_config(workspace_id: str, user=Depends(get_current_user),
                         db=Depends(get_db)):
    """Give the browser a short-lived access token + app id for the Picker."""
    mgr = ConnectionManager(db)
    try:
        token = mgr.access_token(workspace_id=workspace_id)
    except Exception as e:
        raise HTTPException(400, str(e))
    return {
        "access_token": token,
        "app_id": os.getenv("ATLAS_GOOGLE_PROJECT_NUMBER", ""),
        "api_key": os.getenv("ATLAS_GOOGLE_PICKER_API_KEY", ""),
        "client_id": os.getenv("ATLAS_GOOGLE_CLIENT_ID", ""),
    }


# ---- POST /api/v1/connections/google/ingest -------------------------------
class IngestRequest(BaseModel):
    file_ids: List[str]


@router.post("/workspaces/{workspace_id}/connections/google/ingest")
def google_ingest(workspace_id: str, body: IngestRequest,
                  user=Depends(get_current_user), db=Depends(get_db)):
    if not body.file_ids:
        raise HTTPException(400, "Select at least one file.")
    mgr = ConnectionManager(db)
    try:
        token = mgr.access_token(workspace_id=workspace_id)
    except Exception as e:
        raise HTTPException(400, str(e))

    def persist_cb(ws_id: str, fname: str, extension: str, content_bytes: bytes):
        return _persist_drive_file(ws_id, fname, extension, content_bytes, db)

    results = DriveConnector(token).ingest_many(
        body.file_ids, workspace_id=workspace_id, persist=persist_cb)
    return {
        "imported": [
            {"id": r.id, "name": r.name, "kind": r.kind, "ok": r.ok,
             "blocks": r.block_count, "error": r.error, "source_id": r.source_id}
            for r in results
        ],
        "ok_count": sum(1 for r in results if r.ok),
        "fail_count": sum(1 for r in results if not r.ok),
    }


# ---- DELETE /api/v1/connections/google ------------------------------------
@router.delete("/connections/google")
def google_disconnect(workspace_id: str, user=Depends(get_current_user),
                      db=Depends(get_db)):
    return ConnectionManager(db).disconnect(workspace_id=workspace_id)


# ============================================================================
# PATCH 012 - Live Sync (Drive watch channels) routes
# ============================================================================
import logging as _logging
from app.services.connections.livesync import LiveSyncService as _LiveSyncService

_livesync_log = _logging.getLogger("api.livesync")


def _reingest_drive_source(workspace_id: str, source_id: str, filename: str,
                           ext: str, raw: bytes) -> int:
    """Re-ingest a changed file without an empty window (build-then-swap).

    Extracts blocks from the new raw bytes, then delegates to
    reingest_swap which atomically swaps the shadow content in.
    """
    import os
    import tempfile
    from app.services.ingest.dispatcher import detect_kind, extract_blocks
    with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
        tmp.write(raw)
        path = tmp.name
    try:
        blocks = extract_blocks(detect_kind(path), path)
        # reingest_swap is defined in app.services.rag and handles the
        # build-then-swap transaction (new shadow doc -> atomic repoint -> delete old chunks).
        try:
            from app.services.rag import reingest_swap
            reingest_swap(workspace_id, source_id, filename, blocks, origin="google_drive")
        except (ImportError, AttributeError):
            # reingest_swap not yet available; count-only fallback
            _livesync_log.warning("reingest_swap not available; skipping chunk update for %s", source_id)
        return len(blocks)
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


class _LiveSyncToggle(BaseModel):
    enabled: bool
    file_id: str


@router.post("/workspaces/{workspace_id}/sources/{source_id}/livesync")
def set_source_livesync(workspace_id: str, source_id: str, body: _LiveSyncToggle,
                        user=Depends(get_current_user), db: Session = Depends(get_db)):
    mgr = ConnectionManager(db)
    try:
        token = mgr.access_token(workspace_id=workspace_id)
    except Exception as e:
        raise HTTPException(400, str(e))
    svc = _LiveSyncService(db)
    try:
        if body.enabled:
            return svc.enable(workspace_id=workspace_id, source_id=source_id,
                              file_id=body.file_id, access_token=token)
        return svc.disable(workspace_id=workspace_id, source_id=source_id,
                           access_token=token)
    except Exception as e:
        raise HTTPException(400, str(e))


@router.get("/workspaces/{workspace_id}/livesync")
def list_livesync(workspace_id: str, user=Depends(get_current_user),
                  db: Session = Depends(get_db)):
    from app.models import DriveWatchChannel
    rows = (db.query(DriveWatchChannel)
            .filter_by(workspace_id=workspace_id, status="active").all())
    return {"sources": [
        {"source_id": r.source_id, "file_id": r.file_id, "live": True,
         "expiration": r.expiration, "last_synced": r.last_synced}
        for r in rows]}


# PUBLIC webhook: Google calls this on file change. Authenticated by per-channel token.
@router.post("/connections/google/notifications")
async def google_notifications(request: Request, db: Session = Depends(get_db)):
    h = request.headers
    state = h.get("X-Goog-Resource-State", "")
    channel_id = h.get("X-Goog-Channel-ID", "")
    resource_id = h.get("X-Goog-Resource-ID", "")
    token = h.get("X-Goog-Channel-Token", "")

    if state == "sync":
        from fastapi.responses import Response as _Response
        return _Response(status_code=200)   # initial handshake ping, ignore

    svc = _LiveSyncService(db)
    row = svc.resolve_ping(channel_id=channel_id, resource_id=resource_id, token=token)
    if row is None:
        from fastapi.responses import Response as _Response
        return _Response(status_code=200)   # unknown or spoofed ping, ignore safely
    try:
        token_val = ConnectionManager(db).access_token(workspace_id=row.workspace_id)
        svc.apply_change(row, access_token=token_val, reingest=_reingest_drive_source)
    except Exception as e:
        _livesync_log.warning("live sync apply failed for %s: %s", row.source_id, e)
    from fastapi.responses import Response as _Response
    return _Response(status_code=200)


# ============================================================================
# PATCH 013 - Teams / Shared Workspaces routes
# ============================================================================
import logging as _teams_log_mod
from app.services.teams import TeamService as _TeamService, InviteService as _InviteService
from app.services.teams import InviteError as _InviteError

_teams_log = _teams_log_mod.getLogger("api.teams")


def _require_team_role(db, workspace_id: str, user_id: str):
    """Return the caller's role or raise 403 if not a member."""
    role = _TeamService(db).role_of(workspace_id, user_id)
    if role is None:
        raise HTTPException(status_code=403, detail="You are not a member of this workspace.")
    return role


class _InviteBody(BaseModel):
    email: str
    role: str = "viewer"


class _RoleBody(BaseModel):
    role: str


class _AcceptBody(BaseModel):
    token: str


@router.get("/workspaces/{workspace_id}/members")
def list_members(workspace_id: str, user=Depends(get_current_user),
                 db: Session = Depends(get_db)):
    user_id = user.get("sub", "")
    _require_team_role(db, workspace_id, user_id)
    svc = _TeamService(db)
    return {
        "members": svc.members(workspace_id),
        "invites": _InviteService(db).pending(workspace_id),
        "your_role": svc.role_of(workspace_id, user_id),
    }


@router.post("/workspaces/{workspace_id}/invites")
def create_invite(workspace_id: str, body: _InviteBody,
                  user=Depends(get_current_user), db: Session = Depends(get_db)):
    user_id = user.get("sub", "")
    actor_role = _require_team_role(db, workspace_id, user_id)
    try:
        result = _InviteService(db).create(
            actor_role, workspace_id, body.email, body.role, invited_by=user_id
        )
    except _InviteError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))

    # TODO: send invite email here. The raw token is returned ONCE.
    # link = f"{settings.APP_URL}/invite/accept?token={result['token']}"
    # send_invite_email(result["email"], link, workspace_id)
    _teams_log.info("invite created for %s role=%s ws=%s",
                    result["email"], result["role"], workspace_id)
    return {"id": result["id"], "email": result["email"], "role": result["role"],
            "expires_at": result["expires_at"]}  # raw token intentionally NOT returned to client


@router.post("/invites/accept")
def accept_invite(body: _AcceptBody, user=Depends(get_current_user),
                  db: Session = Depends(get_db)):
    user_id = user.get("sub", "")
    user_email = user.get("email", "")
    try:
        return _InviteService(db).accept(body.token, signed_in_email=user_email, user_id=user_id)
    except _InviteError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/workspaces/{workspace_id}/invites/{invite_id}")
def revoke_invite(workspace_id: str, invite_id: str,
                  user=Depends(get_current_user), db: Session = Depends(get_db)):
    actor_role = _require_team_role(db, workspace_id, user.get("sub", ""))
    try:
        ok = _InviteService(db).revoke(actor_role, invite_id)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    return {"revoked": ok}


@router.patch("/workspaces/{workspace_id}/members/{member_user_id}")
def change_member_role(workspace_id: str, member_user_id: str, body: _RoleBody,
                       user=Depends(get_current_user), db: Session = Depends(get_db)):
    actor_role = _require_team_role(db, workspace_id, user.get("sub", ""))
    try:
        _TeamService(db).change_role(actor_role, workspace_id, member_user_id, body.role)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"user_id": member_user_id, "role": body.role}


@router.delete("/workspaces/{workspace_id}/members/{member_user_id}")
def remove_member(workspace_id: str, member_user_id: str,
                  user=Depends(get_current_user), db: Session = Depends(get_db)):
    actor_role = _require_team_role(db, workspace_id, user.get("sub", ""))
    try:
        _TeamService(db).remove(actor_role, workspace_id, member_user_id)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"removed": member_user_id}
