"""Persistent media / Studio jobs with retries, limits, and a stale reaper."""
from __future__ import annotations

import logging
import secrets
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import MediaJob
from . import (
    ACTIVE_JOB_STATUSES,
    MSG_CONCURRENT,
    STATUS_DONE,
    STATUS_FAILED,
    STATUS_PROCESSING,
    STATUS_QUEUED,
    STATUS_WAITING,
    MediaIngestError,
)

logger = logging.getLogger("atlaslm.media.jobs")

STALE_PROCESSING_S = 30 * 60
STALE_WAITING_S = 60 * 60


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def concurrent_count(db: Session, user_id: str) -> int:
    return (
        db.query(MediaJob)
        .filter(MediaJob.user_id == user_id, MediaJob.status.in_(ACTIVE_JOB_STATUSES))
        .count()
    )


def assert_concurrency(db: Session, user_id: str) -> None:
    limit = int(getattr(settings, "ATLAS_MEDIA_CONCURRENT_JOBS", 2) or 2)
    if concurrent_count(db, user_id) >= limit:
        raise MediaIngestError(MSG_CONCURRENT)


def find_idempotent(db: Session, workspace_id: uuid.UUID, key: Optional[str]) -> Optional[MediaJob]:
    if not key:
        return None
    return (
        db.query(MediaJob)
        .filter(MediaJob.workspace_id == workspace_id, MediaJob.idempotency_key == key)
        .first()
    )


def create_job(
    db: Session,
    *,
    user_id: str,
    workspace_id: uuid.UUID,
    kind: str,
    payload: dict[str, Any],
    document_id: Optional[uuid.UUID] = None,
    studio_output_id: Optional[uuid.UUID] = None,
    idempotency_key: Optional[str] = None,
) -> MediaJob:
    existing = find_idempotent(db, workspace_id, idempotency_key)
    if existing:
        return existing
    job = MediaJob(
        id=uuid.uuid4(),
        user_id=user_id,
        workspace_id=workspace_id,
        document_id=document_id,
        studio_output_id=studio_output_id,
        kind=kind,
        status=STATUS_QUEUED,
        stage="queued",
        retry_count=0,
        max_retries=2,
        idempotency_key=idempotency_key,
        callback_token=secrets.token_urlsafe(24),
        payload=payload or {},
        last_heartbeat_at=utcnow(),
    )
    db.add(job)
    db.flush()
    logger.info("job_created job_id=%s kind=%s stage=queued", job.id, kind)
    return job


def mark(
    db: Session,
    job: MediaJob,
    *,
    status: Optional[str] = None,
    stage: Optional[str] = None,
    failure_reason: Optional[str] = None,
    provider_job_id: Optional[str] = None,
    result: Optional[dict[str, Any]] = None,
) -> MediaJob:
    if status:
        job.status = status
    if stage:
        job.stage = stage
    if failure_reason is not None:
        job.failure_reason = failure_reason
    if provider_job_id:
        job.provider_job_id = provider_job_id
    if result is not None:
        job.result = result
    now = utcnow()
    job.updated_at = now
    job.last_heartbeat_at = now
    if status == STATUS_PROCESSING and job.started_at is None:
        job.started_at = now
    if status in {STATUS_DONE, STATUS_FAILED}:
        job.finished_at = now
    db.add(job)
    db.flush()
    logger.info(
        "job_update job_id=%s status=%s stage=%s duration_ms=%s",
        job.id,
        job.status,
        job.stage,
        _duration_ms(job),
    )
    return job


def fail(db: Session, job: MediaJob, reason: str, *, retry: bool = True) -> MediaJob:
    if retry and (job.retry_count or 0) < (job.max_retries or 2):
        job.retry_count = (job.retry_count or 0) + 1
        delay = 2 ** job.retry_count
        job.status = STATUS_QUEUED
        job.stage = "retry_wait"
        job.failure_reason = reason
        job.updated_at = utcnow()
        job.last_heartbeat_at = utcnow() - timedelta(seconds=max(0, 15 - delay))
        db.add(job)
        db.flush()
        logger.info(
            "job_retry job_id=%s retry_count=%s stage=retry_wait",
            job.id,
            job.retry_count,
        )
        return job
    job.status = STATUS_FAILED
    job.stage = "failed"
    job.failure_reason = reason
    job.finished_at = utcnow()
    job.updated_at = utcnow()
    db.add(job)
    db.flush()
    logger.info("job_failed job_id=%s stage=failed", job.id)
    return job


def succeed(db: Session, job: MediaJob, result: Optional[dict[str, Any]] = None) -> MediaJob:
    return mark(db, job, status=STATUS_DONE, stage="done", result=result, failure_reason=None)


def heartbeat(db: Session, job: MediaJob, stage: Optional[str] = None) -> None:
    mark(db, job, stage=stage)


def claim_next(db: Session) -> Optional[MediaJob]:
    now = utcnow()
    candidates = (
        db.query(MediaJob)
        .filter(MediaJob.status == STATUS_QUEUED)
        .order_by(MediaJob.created_at.asc())
        .with_for_update(skip_locked=True)
        .limit(20)
        .all()
    )
    for job in candidates:
        if job.stage == "retry_wait" and job.updated_at:
            updated = job.updated_at
            if updated.tzinfo is None:
                updated = updated.replace(tzinfo=timezone.utc)
            backoff = 2 ** max(1, job.retry_count or 1)
            if (now - updated).total_seconds() < backoff:
                continue
        job.status = STATUS_PROCESSING
        job.stage = job.stage if job.stage not in {"queued", "retry_wait"} else "processing"
        job.started_at = job.started_at or now
        job.last_heartbeat_at = now
        job.updated_at = now
        db.add(job)
        db.flush()
        return job
    return None


def waiting_jobs(db: Session) -> list[MediaJob]:
    return (
        db.query(MediaJob)
        .filter(MediaJob.status == STATUS_WAITING)
        .order_by(MediaJob.updated_at.asc())
        .all()
    )


def reap_stale(db: Session) -> int:
    now = utcnow()
    changed = 0
    rows = (
        db.query(MediaJob)
        .filter(MediaJob.status.in_([STATUS_PROCESSING, STATUS_WAITING, STATUS_QUEUED]))
        .all()
    )
    for job in rows:
        stamp = job.last_heartbeat_at or job.updated_at or job.created_at
        if stamp is None:
            continue
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=timezone.utc)
        age = (now - stamp).total_seconds()
        limit = STALE_WAITING_S if job.status == STATUS_WAITING else STALE_PROCESSING_S
        if job.status == STATUS_QUEUED:
            continue
        if age < limit:
            continue
        reason = (
            "This job stopped while processing. Atlas will retry it, or mark it failed if retries are exhausted."
        )
        if job.status == STATUS_WAITING:
            reason = "Transcription timed out after 60 minutes. Try a shorter file or try again."
        fail(db, job, reason, retry=job.status == STATUS_PROCESSING)
        changed += 1
    if changed:
        db.commit()
    return changed


def get_by_callback(db: Session, token: str) -> Optional[MediaJob]:
    if not token:
        return None
    return db.query(MediaJob).filter(MediaJob.callback_token == token).first()


def callback_url(job: MediaJob) -> Optional[str]:
    base = (getattr(settings, "GLADIA_CALLBACK_BASE", "") or "").rstrip("/")
    if not base or not job.callback_token:
        return None
    return f"{base}/api/v1/internal/media/stt-callback?token={job.callback_token}"


def _duration_ms(job: MediaJob) -> int:
    start = job.started_at or job.created_at
    if not start:
        return 0
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    return int((utcnow() - start).total_seconds() * 1000)


def public_job(job: MediaJob) -> dict[str, Any]:
    return {
        "id": str(job.id),
        "kind": job.kind,
        "status": "done" if job.status == STATUS_DONE else job.status,
        "stage": job.stage,
        "failure_reason": job.failure_reason,
        "document_id": str(job.document_id) if job.document_id else None,
        "studio_output_id": str(job.studio_output_id) if job.studio_output_id else None,
        "retry_count": job.retry_count,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "updated_at": job.updated_at.isoformat() if job.updated_at else None,
    }
