# backend/app/routes/sources.py
"""
Patch 003 source ingestion endpoints.
Handles file uploads (docx/pptx/xlsx/image/audio + existing pdf) and URL sources
(youtube + existing web), routes them through the loader dispatcher, then persists
via the EXISTING chunk -> embed -> pgvector pipeline.
"""
from __future__ import annotations
import os
import tempfile
import uuid
from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.core.database import get_db
from app.services.ingest.dispatcher import detect_kind, extract_blocks
from app.services.pipeline import DocumentPipeline

router = APIRouter(prefix="/api/sources", tags=["sources"])


class UrlSource(BaseModel):
    notebook_id: str
    url: str
    language: str | None = None


async def _persist(notebook_id: str, filename: str, kind: str, blocks, user, db: Session) -> dict:
    try:
        ws_uuid = uuid.UUID(notebook_id) if isinstance(notebook_id, str) else notebook_id
        pipeline = DocumentPipeline(db)
        doc = await pipeline.ingest_extracted_blocks(
            workspace_id=ws_uuid,
            filename=filename,
            file_type=kind,
            blocks=blocks,
            source_url=filename if kind == "youtube" else None,
        )
        return {"ok": True, "source_id": str(doc.id), "block_count": len(blocks)}
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"AtlasLM persistence failed: {str(e)}")


@router.post("/upload")
async def upload_source(
    notebook_id: str = Form(...),
    language: str | None = Form(None),
    file: UploadFile = File(...),
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    suffix = os.path.splitext(file.filename or "")[1].lower()
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(await file.read())
        tmp_path = tmp.name
    try:
        kind = detect_kind(tmp_path)
        if kind in ("unknown",):
            raise HTTPException(status_code=415, detail="Unsupported file type.")
        if kind == "pdf":
            raise HTTPException(status_code=409,
                detail="PDFs are handled by the existing ingestion route.")
        blocks = extract_blocks(kind, tmp_path, language=language)
        if not blocks:
            raise HTTPException(status_code=422,
                detail="AtlasLM could not extract readable content from this source.")
        return await _persist(notebook_id, file.filename or "source", kind, blocks, user, db)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=502,
            detail="AtlasLM could not ingest this source. Please retry.")
    finally:
        try: os.unlink(tmp_path)
        except OSError: pass


@router.post("/url")
async def add_url_source(
    body: UrlSource,
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        kind = detect_kind(body.url)
        if kind == "web":
            raise HTTPException(status_code=409,
                detail="Plain web URLs are handled by the existing crawler route.")
        blocks = extract_blocks(kind, body.url, language=body.language)
        if not blocks:
            raise HTTPException(status_code=422,
                detail="AtlasLM could not retrieve a transcript for this URL.")
        return await _persist(body.notebook_id, body.url, kind, blocks, user, db)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=502,
            detail="AtlasLM could not ingest this URL. Please retry.")
