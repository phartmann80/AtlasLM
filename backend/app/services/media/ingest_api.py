"""HTTP-facing helpers for media ingest. Validation happens before a job exists."""
from __future__ import annotations

import os
import tempfile
import uuid
from pathlib import Path
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import Document
from app.services.jobs import enqueue_media_job, redis_healthy
from app.services.media import (
    AUDIO_EXTENSIONS,
    IMAGE_EXTENSIONS,
    JOB_AUDIO,
    JOB_IMAGE,
    JOB_VIDEO,
    JOB_YOUTUBE,
    KIND_AUDIO,
    KIND_IMAGE,
    KIND_VIDEO,
    KIND_YOUTUBE,
    MEDIA_EXTENSIONS,
    MSG_IMAGE_EMPTY,
    MSG_IMAGE_TOO_LARGE,
    MSG_MEDIA_TOO_LARGE,
    MSG_MEDIA_TOO_LONG,
    MSG_NOT_MEDIA,
    MSG_UNSUPPORTED_IMAGE,
    MSG_UNSUPPORTED_MEDIA,
    MSG_YOUTUBE_INVALID,
    VIDEO_EXTENSIONS,
    MediaIngestError,
)
from app.services.media import ffmpeg as ffmpeg_mod
from app.services.media import image_pipeline
from app.services.media import jobs as jobstore
from app.services.media import storage
from app.services.media import youtube as youtube_mod
from app.services.pipeline import DocumentPipeline


def classify_filename(filename: str) -> Optional[str]:
    ext = Path(filename or "").suffix.lower()
    if ext in IMAGE_EXTENSIONS:
        return KIND_IMAGE
    if ext in AUDIO_EXTENSIONS:
        return KIND_AUDIO
    if ext in VIDEO_EXTENSIONS:
        return KIND_VIDEO
    return None


def validate_and_stage_file(filename: str, data: bytes) -> dict:
    kind = classify_filename(filename)
    if kind == KIND_IMAGE:
        ext = image_pipeline.validate_image_upload(
            filename, data, max_mb=int(getattr(settings, "ATLAS_IMAGE_MAX_MB", 20) or 20)
        )
        return {"kind": KIND_IMAGE, "job_kind": JOB_IMAGE, "ext": ext}
    if kind in {KIND_AUDIO, KIND_VIDEO}:
        max_mb = int(getattr(settings, "ATLAS_MEDIA_MAX_MB", 2048) or 2048)
        if len(data) > max_mb * 1024 * 1024:
            raise MediaIngestError(MSG_MEDIA_TOO_LARGE)
        suffix = Path(filename).suffix.lower() or ".bin"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(data)
            tmp_path = tmp.name
        try:
            probe = ffmpeg_mod.probe(tmp_path)
        except MediaIngestError:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise MediaIngestError(MSG_NOT_MEDIA)
        max_seconds = int(getattr(settings, "ATLAS_MEDIA_MAX_SECONDS", 10800) or 10800)
        if float(probe.get("duration") or 0) > max_seconds:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise MediaIngestError(MSG_MEDIA_TOO_LONG)
        if kind == KIND_VIDEO and not probe.get("has_audio") and not probe.get("has_video"):
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise MediaIngestError(MSG_NOT_MEDIA)
        return {
            "kind": kind,
            "job_kind": JOB_VIDEO if kind == KIND_VIDEO else JOB_AUDIO,
            "tmp_path": tmp_path,
            "duration": probe["duration"],
        }
    raise MediaIngestError(
        "Invalid file format. Supported: PDF, DOCX, XLSX, PPTX, TXT, MD, CSV, "
        "PNG, JPG, WEBP, HEIC, MP3, WAV, M4A, AAC, OGG, FLAC, MP4, MOV, WEBM, MKV."
    )


def validate_media_path(filename: str, path: str, size_bytes: int) -> dict:
    kind = classify_filename(filename)
    if kind == KIND_IMAGE:
        max_mb = int(getattr(settings, "ATLAS_IMAGE_MAX_MB", 20) or 20)
        if size_bytes > max_mb * 1024 * 1024:
            raise MediaIngestError(MSG_IMAGE_TOO_LARGE)
        if size_bytes < 32:
            raise MediaIngestError(MSG_IMAGE_EMPTY)
        ext = Path(filename).suffix.lower()
        if ext not in IMAGE_EXTENSIONS:
            raise MediaIngestError(MSG_UNSUPPORTED_IMAGE)
        return {"kind": KIND_IMAGE, "job_kind": JOB_IMAGE, "ext": ext, "tmp_path": path}
    if kind in {KIND_AUDIO, KIND_VIDEO}:
        max_mb = int(getattr(settings, "ATLAS_MEDIA_MAX_MB", 2048) or 2048)
        if size_bytes > max_mb * 1024 * 1024:
            raise MediaIngestError(MSG_MEDIA_TOO_LARGE)
        try:
            probe = ffmpeg_mod.probe(path)
        except MediaIngestError:
            raise MediaIngestError(MSG_NOT_MEDIA)
        max_seconds = int(getattr(settings, "ATLAS_MEDIA_MAX_SECONDS", 10800) or 10800)
        if float(probe.get("duration") or 0) > max_seconds:
            raise MediaIngestError(MSG_MEDIA_TOO_LONG)
        if not probe.get("has_audio") and not probe.get("has_video"):
            raise MediaIngestError(MSG_NOT_MEDIA)
        return {
            "kind": kind,
            "job_kind": JOB_VIDEO if kind == KIND_VIDEO else JOB_AUDIO,
            "tmp_path": path,
            "duration": probe["duration"],
        }
    raise MediaIngestError(
        "Invalid file format. Supported: PDF, DOCX, XLSX, PPTX, TXT, MD, CSV, "
        "PNG, JPG, WEBP, HEIC, MP3, WAV, M4A, AAC, OGG, FLAC, MP4, MOV, WEBM, MKV."
    )


def start_media_document(
    db: Session,
    *,
    user_id: str,
    workspace_id: uuid.UUID,
    filename: str,
    data: bytes,
    language: Optional[str],
    idempotency_key: Optional[str],
) -> Document:
    staged = validate_and_stage_file(filename, data)
    return _persist_media_document(
        db,
        user_id=user_id,
        workspace_id=workspace_id,
        filename=filename,
        staged=staged,
        data=data,
        source_path=staged.get("tmp_path") if staged.get("kind") != KIND_IMAGE else None,
        language=language,
        idempotency_key=idempotency_key,
    )


def start_media_document_from_path(
    db: Session,
    *,
    user_id: str,
    workspace_id: uuid.UUID,
    filename: str,
    path: str,
    size_bytes: int,
    language: Optional[str],
    idempotency_key: Optional[str],
) -> Document:
    staged = validate_media_path(filename, path, size_bytes)
    return _persist_media_document(
        db,
        user_id=user_id,
        workspace_id=workspace_id,
        filename=filename,
        staged=staged,
        data=None,
        source_path=path,
        language=language,
        idempotency_key=idempotency_key,
        unlink_source=True,
    )


def _persist_media_document(
    db: Session,
    *,
    user_id: str,
    workspace_id: uuid.UUID,
    filename: str,
    staged: dict,
    data: Optional[bytes],
    source_path: Optional[str],
    language: Optional[str],
    idempotency_key: Optional[str],
    unlink_source: bool = False,
) -> Document:
    jobstore.assert_concurrency(db, user_id)
    pipeline = DocumentPipeline(db)
    document = pipeline.create_pending_document(
        workspace_id=workspace_id,
        filename=filename,
        file_type=staged["kind"],
        idempotency_key=idempotency_key,
    )
    if data is not None:
        stored = storage.save_source_file(workspace_id, document.id, filename, data)
    else:
        stored = storage.save_source_path(workspace_id, document.id, filename, source_path or "")
    document.storage_path = stored
    if staged.get("duration"):
        document.media_duration_ms = int(float(staged["duration"]) * 1000)
    db.add(document)
    payload = {
        "storage_path": stored,
        "language": language,
        "filename": filename,
    }
    job = jobstore.create_job(
        db,
        user_id=user_id,
        workspace_id=workspace_id,
        kind=staged["job_kind"],
        payload=payload,
        document_id=document.id,
        idempotency_key=idempotency_key,
    )
    db.commit()
    if redis_healthy():
        try:
            enqueue_media_job(job.id)
        except Exception:
            pass
    tmp_path = staged.get("tmp_path") if unlink_source or staged.get("kind") != KIND_IMAGE else None
    if unlink_source and source_path:
        tmp_path = source_path
    if tmp_path and os.path.abspath(tmp_path) != os.path.abspath(stored):
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
    return document


def requeue_media_document(
    db: Session,
    *,
    user_id: str,
    document: Document,
    language: Optional[str],
    idempotency_key: Optional[str],
) -> Document:
    kind = (document.file_type or "").lower()
    job_kind = {
        KIND_IMAGE: JOB_IMAGE,
        KIND_AUDIO: JOB_AUDIO,
        KIND_VIDEO: JOB_VIDEO,
        KIND_YOUTUBE: JOB_YOUTUBE,
    }.get(kind)
    if not job_kind:
        raise MediaIngestError("This source cannot be retried as media.")
    if kind != KIND_YOUTUBE and not (document.storage_path and os.path.exists(document.storage_path)):
        raise MediaIngestError("The original file is no longer available. Upload it again.")
    jobstore.assert_concurrency(db, user_id)
    document.status = "processing"
    document.error_message = None
    db.add(document)
    payload = {
        "storage_path": document.storage_path,
        "language": language,
        "filename": document.filename,
        "url": document.source_url,
        "video_id": document.youtube_video_id,
    }
    job = jobstore.create_job(
        db,
        user_id=user_id,
        workspace_id=document.workspace_id,
        kind=job_kind,
        payload=payload,
        document_id=document.id,
        idempotency_key=idempotency_key,
    )
    db.commit()
    if redis_healthy():
        try:
            enqueue_media_job(job.id)
        except Exception:
            pass
    return document


def start_youtube_document(
    db: Session,
    *,
    user_id: str,
    workspace_id: uuid.UUID,
    url: str,
    language: Optional[str],
    idempotency_key: Optional[str],
) -> Document:
    video_id = youtube_mod.extract_video_id(url)
    if not video_id:
        raise MediaIngestError(MSG_YOUTUBE_INVALID)
    jobstore.assert_concurrency(db, user_id)
    pipeline = DocumentPipeline(db)
    canonical = youtube_mod.canonical_url(video_id, youtube_mod.start_seconds(url))
    document = pipeline.create_pending_document(
        workspace_id=workspace_id,
        filename=f"YouTube {video_id}",
        file_type=KIND_YOUTUBE,
        source_url=canonical,
        idempotency_key=idempotency_key,
    )
    document.youtube_video_id = video_id
    db.add(document)
    job = jobstore.create_job(
        db,
        user_id=user_id,
        workspace_id=workspace_id,
        kind=JOB_YOUTUBE,
        payload={"url": url, "language": language, "video_id": video_id},
        document_id=document.id,
        idempotency_key=idempotency_key,
    )
    db.commit()
    if redis_healthy():
        try:
            enqueue_media_job(job.id)
        except Exception:
            pass
    return document


def http_error(exc: MediaIngestError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=exc.public_message)
