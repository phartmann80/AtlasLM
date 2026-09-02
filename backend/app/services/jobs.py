"""
AtlasLM ingestion job queue (Patch 003).

Redis-backed FIFO queue decoupling document ingestion from the HTTP
request path. The API enqueues a job + payload; the worker process
(app/worker.py) consumes it and runs the DocumentPipeline.

Design notes:
- File bytes are stored in a separate Redis key (atlaslm:job:payload:<id>)
  with a TTL so an abandoned queue cannot grow unbounded.
- The job envelope (metadata) is JSON; the payload is raw bytes.
- Queue key: atlaslm:ingest:queue (BRPOP by worker, LPUSH by API).
- All keys are namespaced under 'atlaslm:'.
"""

import json
import logging
import uuid
from typing import Any, Dict, Optional

import redis

from ..core.config import settings

logger = logging.getLogger("atlaslm.jobs")

QUEUE_KEY = "atlaslm:ingest:queue"
PAYLOAD_KEY_TMPL = "atlaslm:job:payload:{job_id}"
META_KEY_TMPL = "atlaslm:job:meta:{job_id}"

# Payloads expire after 2 hours if never consumed; metadata after 24h.
PAYLOAD_TTL_SECONDS = 2 * 60 * 60
META_TTL_SECONDS = 24 * 60 * 60

_pool: Optional[redis.ConnectionPool] = None


def get_redis() -> redis.Redis:
    global _pool
    if _pool is None:
        _pool = redis.ConnectionPool.from_url(
            settings.REDIS_URL, decode_responses=False
        )
    return redis.Redis(connection_pool=_pool)


def enqueue_ingestion_job(
    *,
    document_id: uuid.UUID,
    workspace_id: uuid.UUID,
    filename: str,
    file_type: str,
    file_bytes: bytes,
    source_url: Optional[str] = None,
    language: Optional[str] = None,
) -> str:
    """
    Store payload + metadata and push the job id onto the queue.
    Returns the job id. Raises redis.RedisError on connectivity failure
    (caller decides whether to fall back to synchronous ingestion).
    """
    r = get_redis()
    job_id = str(uuid.uuid4())

    meta: Dict[str, Any] = {
        "job_id": job_id,
        "document_id": str(document_id),
        "workspace_id": str(workspace_id),
        "filename": filename,
        "file_type": file_type,
        "source_url": source_url,
        "language": language,
    }

    pipe = r.pipeline()
    pipe.set(
        PAYLOAD_KEY_TMPL.format(job_id=job_id),
        file_bytes,
        ex=PAYLOAD_TTL_SECONDS,
    )
    pipe.set(
        META_KEY_TMPL.format(job_id=job_id),
        json.dumps(meta).encode("utf-8"),
        ex=META_TTL_SECONDS,
    )
    pipe.lpush(QUEUE_KEY, job_id.encode("utf-8"))
    pipe.execute()

    logger.info(
        "Enqueued ingestion job %s for document %s (%s, %d bytes)",
        job_id, document_id, filename, len(file_bytes),
    )
    return job_id


def pop_ingestion_job(timeout: int = 5) -> Optional[Dict[str, Any]]:
    """
    Blocking pop of the next job. Returns dict with 'meta' and
    'file_bytes', or None on timeout. Payload keys are deleted on read.
    """
    r = get_redis()
    item = r.brpop(QUEUE_KEY, timeout=timeout)
    if item is None:
        return None

    job_id = item[1].decode("utf-8")
    meta_raw = r.get(META_KEY_TMPL.format(job_id=job_id))
    payload = r.get(PAYLOAD_KEY_TMPL.format(job_id=job_id))
    r.delete(PAYLOAD_KEY_TMPL.format(job_id=job_id))

    if meta_raw is None or payload is None:
        logger.warning("Job %s popped but payload/meta expired; skipping.", job_id)
        return None

    meta = json.loads(meta_raw.decode("utf-8"))
    return {"meta": meta, "file_bytes": payload}


def redis_healthy() -> bool:
    try:
        return bool(get_redis().ping())
    except Exception:
        return False


STUDIO_QUEUE_KEY = "atlaslm:studio:queue"
MEDIA_QUEUE_KEY = "atlaslm:media:queue"


def enqueue_studio_job(
    *,
    output_id: uuid.UUID,
    scope_doc_ids: Optional[list[uuid.UUID]] = None,
) -> str:
    """
    Push a Studio generation job. Raises redis.RedisError on connectivity
    failure (caller decides whether to fall back to synchronous generation).
    """
    r = get_redis()
    job_id = str(uuid.uuid4())
    envelope = json.dumps(
        {
            "job_id": job_id,
            "output_id": str(output_id),
            "scope_doc_ids": [str(x) for x in scope_doc_ids] if scope_doc_ids is not None else None,
        }
    ).encode("utf-8")
    r.lpush(STUDIO_QUEUE_KEY, envelope)
    logger.info("Enqueued studio job %s for output %s", job_id, output_id)
    return job_id


def pop_studio_job(timeout: int = 5):
    """Blocking pop of the next Studio job, or None on timeout."""
    r = get_redis()
    item = r.brpop(STUDIO_QUEUE_KEY, timeout=timeout)
    if item is None:
        return None
    return json.loads(item[1].decode("utf-8"))


def enqueue_media_job(job_id: uuid.UUID) -> None:
    r = get_redis()
    r.lpush(MEDIA_QUEUE_KEY, str(job_id).encode("utf-8"))
    logger.info("Enqueued media job %s", job_id)


def pop_media_wakeup(timeout: int = 2) -> Optional[str]:
    r = get_redis()
    item = r.brpop(MEDIA_QUEUE_KEY, timeout=timeout)
    if item is None:
        return None
    return item[1].decode("utf-8")

