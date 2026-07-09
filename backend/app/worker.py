"""
AtlasLM ingestion worker (Patch 003).

Standalone process consuming ingestion jobs from Redis and running the
DocumentPipeline outside the HTTP request path.

Run via:  python -m app.worker
Deployed as the 'worker' service in docker-compose (same image as backend).

Flow per job:
1. Pop job (meta + file bytes) from Redis.
2. Load the placeholder Document row (status='processing').
3. Run parse -> chunk -> embed -> persist chunks.
4. Mark document status='ready' (or 'failed' with a public error message).

Crash-safety: every job is wrapped; a failure marks the document
'failed' and the worker continues. The worker never fabricates data.
"""

import asyncio
import logging
import signal
import uuid

from .core.database import SessionLocal
from .core.providers import ProviderError
from .models import Document
from .services.jobs import pop_ingestion_job, pop_studio_job, redis_healthy
from .services.pipeline import DocumentPipeline

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(name)s] [%(levelname)s] %(message)s",
)
# Suppress httpx request logger to prevent provider URL leaks in logs (T11)
logging.getLogger("httpx").setLevel(logging.WARNING)

logger = logging.getLogger("atlaslm.worker")

_shutdown = False


def _handle_signal(signum, frame):
    global _shutdown
    logger.info("Received signal %s; finishing current job then exiting.", signum)
    _shutdown = True


async def process_job(job: dict) -> None:
    meta = job["meta"]
    file_bytes = job["file_bytes"]
    document_id = uuid.UUID(meta["document_id"])

    db = SessionLocal()
    try:
        document = db.query(Document).filter(Document.id == document_id).first()
        if document is None:
            # Document was deleted while queued; drop the job silently.
            logger.info("Document %s no longer exists; skipping job %s.",
                        document_id, meta["job_id"])
            return

        pipeline = DocumentPipeline(db)
        try:
            await pipeline.run_ingestion_for_document(
                document=document,
                file_bytes=file_bytes,
                file_type=meta["file_type"],
                language=meta.get("language"),
            )
            document.status = "ready"
            document.error_message = None
            db.commit()
            logger.info("Job %s complete: document %s ready.",
                        meta["job_id"], document_id)
        except ProviderError as e:
            db.rollback()
            document = db.query(Document).filter(Document.id == document_id).first()
            if document:
                document.status = "failed"
                document.error_message = e.public_message
                db.commit()
            logger.error("Job %s failed (provider): %s", meta["job_id"], e.public_message)
        except ValueError as e:
            db.rollback()
            document = db.query(Document).filter(Document.id == document_id).first()
            if document:
                document.status = "failed"
                document.error_message = str(e)
                db.commit()
            logger.error("Job %s failed (parse/validation): %s", meta["job_id"], e)
        except Exception as e:
            db.rollback()
            document = db.query(Document).filter(Document.id == document_id).first()
            if document:
                document.status = "failed"
                document.error_message = (
                    "An unexpected error occurred while processing this document."
                )
                db.commit()
            logger.error("Job %s failed (unexpected): %s", meta["job_id"], e, exc_info=True)
    finally:
        db.close()


async def process_studio_job(job: dict) -> None:
    """Consumes the studio queue job enqueued by create_studio_output. Runs the
    scoped retrieval (same as chat), generates the artifact, validates, saves."""
    from .services.studio_outputs import generate_studio_output, StudioGenerationError
    from .services.rag import retrieve_chunks
    from .models import StudioOutput, StudioOutputCitation
    from .core.database import SessionLocal

    output_id = job.get("output_id")
    scope_doc_ids_str = job.get("scope_doc_ids")
    scope_doc_ids = [uuid.UUID(x) for x in scope_doc_ids_str] if scope_doc_ids_str is not None else None

    db = SessionLocal()
    try:
        output = db.get(StudioOutput, uuid.UUID(output_id))
        if not output:
            logger.error("Studio output %s not found in DB", output_id)
            return

        output.status = "processing"
        output.error = None
        db.commit()

        # Seed query
        def _seed_query(output_type: str) -> str:
            return {
                "mind_map": "key concepts, central topics, and relationships across the sources",
                "study_guide": "key concepts, definitions, main points, and summaries across the sources",
                "quiz": "key facts, assertions, claims, and detailed information across the sources",
                "flashcards": "key concepts, vocabulary, facts, and Q&A details across the sources",
            }.get(output_type, "key concepts and main points across the sources")

        from .services.studio_outputs import TOP_K
        chunks = retrieve_chunks(
            notebook_id=str(output.workspace_id),
            query=_seed_query(output.output_type),
            source_ids=[str(x) for x in scope_doc_ids] if scope_doc_ids is not None else [],
            k=TOP_K[output.output_type],
        )

        content, citations = generate_studio_output(output.output_type, chunks)
        output.content = content
        output.status = "ready"
        output.error = None

        db.add_all([
            StudioOutputCitation(
                studio_output_id=output.id,
                document_id=uuid.UUID(c["document_id"]) if isinstance(c["document_id"], str) else c["document_id"],
                page_number=c.get("page_number")
            )
            for c in citations
        ])
        db.commit()
        logger.info("Studio job %s complete: output ready.", output_id)
    except StudioGenerationError as e:
        db.rollback()
        output = db.get(StudioOutput, uuid.UUID(output_id))
        if output:
            output.status = "failed"
            output.error = str(e)
            db.commit()
        logger.error("Studio job %s failed: %s", output_id, e)
    except Exception as e:
        db.rollback()
        output = db.get(StudioOutput, uuid.UUID(output_id))
        if output:
            output.status = "failed"
            output.error = "Generation failed. Please try again."
            db.commit()
        logger.error("Studio job %s failed (unexpected): %s", output_id, e, exc_info=True)
    finally:
        db.close()


async def main() -> None:
    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    if not redis_healthy():
        logger.warning("Redis not reachable at startup; will keep retrying.")

    # Start the deep research worker queue thread
    import threading
    from .services.research.worker_handler import handle_research_queue
    threading.Thread(target=handle_research_queue, daemon=True).start()

    # Start the Drive watch-channel renewal sweep thread (Patch 012)
    from .services.connections.renewal_worker import run_forever as _watch_renewal
    threading.Thread(target=_watch_renewal, daemon=True, name="watch-renewal").start()

    logger.info("AtlasLM ingestion worker started.")
    while not _shutdown:
        try:
            job = await asyncio.to_thread(pop_ingestion_job, 3)
            if job:
                await process_job(job)
                continue

            studio_job = await asyncio.to_thread(pop_studio_job, 2)
            if studio_job:
                await process_studio_job(studio_job)
                continue
        except Exception as e:
            logger.error("Queue pop failure: %s; retrying in 5s.", e)
            await asyncio.sleep(5)
            continue

    logger.info("Worker shut down cleanly.")


if __name__ == "__main__":
    asyncio.run(main())

