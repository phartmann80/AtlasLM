"""Run a media ingest job end to end and persist citable chunks."""
from __future__ import annotations

import logging
import os
import tempfile
import time
import uuid
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models import Document, DocumentChunk, MediaJob
from app.services.pipeline import DocumentPipeline
from . import (
    JOB_AUDIO,
    JOB_IMAGE,
    JOB_VIDEO,
    JOB_YOUTUBE,
    KIND_AUDIO,
    KIND_IMAGE,
    KIND_VIDEO,
    KIND_YOUTUBE,
    MSG_GLADIA_TIMEOUT,
    MSG_MEDIA_TOO_LARGE,
    MSG_MEDIA_TOO_LONG,
    MSG_NOT_MEDIA,
    MSG_YOUTUBE_INVALID,
    STATUS_WAITING,
    MediaIngestError,
)
from . import ffmpeg as ffmpeg_mod
from . import gladia
from . import image_pipeline
from . import jobs as jobstore
from . import youtube as youtube_mod

logger = logging.getLogger("atlaslm.media.runner")


def persist_blocks(db: Session, document: Document, blocks: list[dict[str, Any]]) -> int:
    pipeline = DocumentPipeline(db)

    async def _run():
        contents = [b["text"] for b in blocks]
        embeddings = await pipeline.generate_embeddings_with_retry(contents=contents)
        if len(embeddings) != len(blocks):
            raise ValueError("Embedding count mismatch during media ingest.")
        from app.core.providers import provider_registry
        document.embedding_model = provider_registry.get_embeddings(None).model_id
        db.query(DocumentChunk).filter(DocumentChunk.document_id == document.id).delete()
        for idx, block in enumerate(blocks):
            text = block["text"]
            offset = int(block.get("char_offset") or 0)
            timestamp = block.get("timestamp")
            start_ms = block.get("start_ms")
            if start_ms is None and timestamp is not None:
                start_ms = int(round(float(timestamp) * 1000))
            end_ms = block.get("end_ms")
            db.add(
                DocumentChunk(
                    id=uuid.uuid4(),
                    document_id=document.id,
                    content=text,
                    embedding=embeddings[idx],
                    page_number=block.get("page") or (idx + 1),
                    chunk_index=idx,
                    char_start=offset,
                    char_end=offset + len(text),
                    sheet=block.get("sheet"),
                    timestamp=timestamp if timestamp is not None else (
                        (start_ms / 1000.0) if start_ms is not None else None
                    ),
                    source_kind=block.get("source_kind"),
                    speaker=block.get("speaker"),
                    start_ms=start_ms,
                    end_ms=end_ms,
                    region=block.get("region"),
                    video_id=block.get("video_id") or document.youtube_video_id,
                )
            )
        db.flush()

    import asyncio
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        asyncio.run(_run())
    else:
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            pool.submit(lambda: asyncio.run(_run())).result()
    return len(blocks)


def process_job(db: Session, job: MediaJob) -> None:
    started = time.monotonic()
    kind = job.kind
    try:
        if kind == JOB_IMAGE:
            _run_image(db, job)
        elif kind in {JOB_AUDIO, JOB_VIDEO}:
            _run_av_submit(db, job)
        elif kind == JOB_YOUTUBE:
            _run_youtube(db, job)
        else:
            from app.services.studio_gen.runner import process_studio_job
            process_studio_job(db, job)
        duration_ms = int((time.monotonic() - started) * 1000)
        logger.info("job_stage_done job_id=%s kind=%s duration_ms=%s", job.id, kind, duration_ms)
    except MediaIngestError as exc:
        _fail_document(db, job, exc.public_message)
        raise
    except Exception:
        logger.exception("job_unexpected job_id=%s kind=%s", job.id, kind)
        _fail_document(db, job, "Atlas could not finish processing this source. Try again.")
        raise


def _document(db: Session, job: MediaJob) -> Document:
    document = db.query(Document).filter(Document.id == job.document_id).first()
    if not document:
        raise MediaIngestError("This source was removed before processing finished.")
    return document


def _fail_document(db: Session, job: MediaJob, reason: str) -> None:
    jobstore.fail(db, job, reason)
    if job.document_id:
        document = db.query(Document).filter(Document.id == job.document_id).first()
        if document and document.status != "ready":
            document.status = "failed"
            document.error_message = reason
            db.add(document)
    db.commit()


def _ready_document(db: Session, document: Document) -> None:
    document.status = "ready"
    document.error_message = None
    db.add(document)


def _run_image(db: Session, job: MediaJob) -> None:
    document = _document(db, job)
    jobstore.heartbeat(db, job, stage="ocr")
    payload = job.payload or {}
    src = payload.get("storage_path") or document.storage_path
    if not src or not os.path.exists(src):
        raise MediaIngestError("The uploaded image is no longer available. Upload it again.")
    work_dir = os.path.dirname(src)
    blocks, normalized = image_pipeline.process_image_file(src, document.filename, work_dir)
    document.storage_path = normalized
    jobstore.heartbeat(db, job, stage="embed")
    persist_blocks(db, document, blocks)
    document.extra_metadata = {
        **(document.extra_metadata or {}),
        "ocr_chars": sum(len(b["text"]) for b in blocks if b.get("source_kind") == "image_ocr"),
        "has_vision": any(b.get("source_kind") == "image_vision" for b in blocks),
    }
    _ready_document(db, document)
    jobstore.succeed(db, job, {"chunks": len(blocks)})
    db.commit()


def _validate_media_limits(probe: dict[str, Any]) -> None:
    from app.core.config import settings
    max_seconds = int(getattr(settings, "ATLAS_MEDIA_MAX_SECONDS", 10800) or 10800)
    duration = float(probe.get("duration") or 0)
    if duration > max_seconds:
        raise MediaIngestError(MSG_MEDIA_TOO_LONG)


def _run_av_submit(db: Session, job: MediaJob) -> None:
    document = _document(db, job)
    payload = job.payload or {}
    src = payload.get("storage_path") or document.storage_path
    if not src or not os.path.exists(src):
        raise MediaIngestError("The uploaded media file is no longer available. Upload it again.")
    jobstore.heartbeat(db, job, stage="ffprobe")
    probe = ffmpeg_mod.probe(src)
    _validate_media_limits(probe)
    document.media_duration_ms = int(probe["duration"] * 1000)
    work = os.path.dirname(src)
    flac_path = os.path.join(work, "normalized.flac")
    jobstore.heartbeat(db, job, stage="ffmpeg")
    ffmpeg_mod.to_flac_mono_16k(src, flac_path)
    jobstore.heartbeat(db, job, stage="stt_upload")
    uploaded = gladia.upload_audio(flac_path)
    audio_url = uploaded.get("audio_url")
    if not audio_url:
        raise MediaIngestError("Atlas could not upload this recording for transcription. Try again.")
    callback = jobstore.callback_url(job)
    jobstore.heartbeat(db, job, stage="stt_submit")
    started = gladia.start_transcription(audio_url, callback_url=callback)
    provider_id = started.get("id")
    job.payload = {**(job.payload or {}), "flac_path": flac_path, "audio_url": audio_url}
    jobstore.mark(
        db, job,
        status=STATUS_WAITING,
        stage="stt_waiting",
        provider_job_id=provider_id,
    )
    db.commit()
    logger.info(
        "stt_waiting job_id=%s source_id=%s audio_duration=%s",
        job.id,
        document.id,
        (uploaded.get("audio_metadata") or {}).get("audio_duration"),
    )


def _transcription_ready(payload: Optional[dict[str, Any]]) -> bool:
    if not payload or not isinstance(payload, dict):
        return False
    body = payload.get("payload") if isinstance(payload.get("payload"), dict) else payload
    result = body.get("result") or body
    transcription = result.get("transcription") or {}
    return bool(
        transcription.get("utterances")
        or transcription.get("segments")
        or transcription.get("full_transcript")
    )


def complete_stt_job(db: Session, job: MediaJob, payload: Optional[dict[str, Any]] = None) -> bool:
    document = _document(db, job)
    data = payload if _transcription_ready(payload) else None
    if data and isinstance(data.get("payload"), dict) and not (data.get("result") or data.get("transcription")):
        data = data["payload"]
    if data is None:
        if not job.provider_job_id:
            raise MediaIngestError(MSG_GLADIA_TIMEOUT)
        data = gladia.get_transcription(job.provider_job_id)
        status = (data.get("status") or "").lower()
        if status not in {"done", "success", "completed"}:
            if status in {"error", "failed"}:
                raise MediaIngestError(
                    "Transcription failed for this recording. Try a different file or try again."
                )
            jobstore.heartbeat(db, job, stage="stt_waiting")
            db.commit()
            return False
    jobstore.heartbeat(db, job, stage="chunk")
    utterances = gladia.extract_utterances(data)
    if not utterances:
        raise MediaIngestError(
            "Atlas could not find spoken words in this recording. Try a clearer file."
        )
    windows = gladia.group_utterances(utterances)
    youtube_id = document.youtube_video_id or (job.payload or {}).get("video_id")
    source_kind = "youtube" if youtube_id else ("video" if job.kind == JOB_VIDEO else "audio")
    for window in windows:
        window["source_kind"] = source_kind
        window["page"] = 1
        if youtube_id:
            window["video_id"] = youtube_id
    jobstore.heartbeat(db, job, stage="embed")
    persist_blocks(db, document, windows)
    audio_duration = None
    result = data.get("result") or data
    audio_duration = (result.get("metadata") or {}).get("audio_duration")
    document.extra_metadata = {
        **(document.extra_metadata or {}),
        "audio_duration": audio_duration,
        "utterances": len(utterances),
        "speakers": sorted({u["speaker"] for u in utterances}),
    }
    if audio_duration:
        document.media_duration_ms = int(float(audio_duration) * 1000)
        logger.info(
            "stt_complete job_id=%s source_id=%s audio_duration=%s",
            job.id, document.id, audio_duration,
        )
    _ready_document(db, document)
    jobstore.succeed(db, job, {"chunks": len(windows), "audio_duration": audio_duration})
    db.commit()
    return True


def _run_youtube(db: Session, job: MediaJob) -> None:
    document = _document(db, job)
    url = (job.payload or {}).get("url") or document.source_url
    if not url:
        raise MediaIngestError(MSG_YOUTUBE_INVALID)
    video_id = youtube_mod.extract_video_id(url)
    if not video_id:
        raise MediaIngestError(MSG_YOUTUBE_INVALID)
    document.youtube_video_id = video_id
    document.source_url = youtube_mod.canonical_url(video_id, youtube_mod.start_seconds(url))
    jobstore.heartbeat(db, job, stage="metadata")
    meta = {}
    try:
        meta = youtube_mod.dump_metadata(url)
        from . import MSG_YOUTUBE_AGE, MSG_YOUTUBE_LIVE, MSG_YOUTUBE_PRIVATE
        availability = str(meta.get("availability") or "").lower()
        live_status = str(meta.get("live_status") or "").lower()
        if meta.get("is_live") or live_status in {"is_live", "live"}:
            raise MediaIngestError(MSG_YOUTUBE_LIVE)
        if meta.get("age_limit") and int(meta.get("age_limit") or 0) >= 18:
            raise MediaIngestError(MSG_YOUTUBE_AGE)
        if availability == "private" or meta.get("is_private"):
            raise MediaIngestError(MSG_YOUTUBE_PRIVATE)
    except MediaIngestError:
        raise
    except Exception:
        meta = {}
    oembed = youtube_mod.fetch_oembed(video_id)
    card = youtube_mod.card_from_meta(video_id, meta, oembed)
    document.filename = f"{card['title'][:200]} (YouTube)"
    document.channel_name = card.get("channel") or None
    document.thumbnail_path = card.get("thumbnail")
    document.extra_metadata = {**(document.extra_metadata or {}), **card}
    if card.get("duration"):
        try:
            document.media_duration_ms = int(float(card["duration"]) * 1000)
        except (TypeError, ValueError):
            pass
    jobstore.heartbeat(db, job, stage="captions")
    cues: list[dict[str, Any]] = []
    try:
        cues = youtube_mod.fetch_captions(video_id, (job.payload or {}).get("language"))
    except MediaIngestError:
        raise
    except Exception:
        cues = []
    if cues:
        windows = youtube_mod.caption_windows(cues)
        for window in windows:
            window["video_id"] = video_id
            window["source_kind"] = "youtube"
            window["page"] = 1
        jobstore.heartbeat(db, job, stage="embed")
        persist_blocks(db, document, windows)
        _ready_document(db, document)
        jobstore.succeed(db, job, {"chunks": len(windows), "path": "captions"})
        db.commit()
        return
    jobstore.heartbeat(db, job, stage="audio_fallback")
    work = tempfile.mkdtemp(prefix="atlas-yt-")
    try:
        audio_path = youtube_mod.download_audio(url, work)
    except MediaIngestError:
        raise
    except Exception as exc:
        from . import MSG_YOUTUBE_BLOCKED
        raise MediaIngestError(MSG_YOUTUBE_BLOCKED) from exc
    job.payload = {**(job.payload or {}), "storage_path": audio_path, "work_dir": work}
    job.kind = JOB_AUDIO
    document.file_type = KIND_YOUTUBE
    db.add(document)
    db.commit()
    _run_av_submit(db, job)
