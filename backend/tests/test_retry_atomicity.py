"""Retry must not persist a chunk delete when embedding fails synchronously."""

from __future__ import annotations

import asyncio
import os
import sys
import unittest
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

os.environ.setdefault("JWT_SECRET", "test-jwt-secret")
os.environ.setdefault("DATABASE_URL", "postgresql://atlaslm@localhost:5435/atlaslm_db")

for _name in (
    "fitz",
    "faster_whisper",
    "yt_dlp",
    "youtube_transcript_api",
    "pytesseract",
    "PIL",
    "docx",
    "openpyxl",
    "pptx",
    "bs4",
    "lxml",
    "pandas",
    "reportlab",
    "cryptography",
):
    sys.modules.setdefault(_name, MagicMock())

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from app.api.endpoints import router
from app.core.database import get_db
from app.models import Document, DocumentChunk
from app.services.pipeline import DocumentPipeline


OWNER = "owner-1"
WORKSPACE_ID = uuid.uuid4()
DOCUMENT_ID = uuid.uuid4()


class FakeDoc:
    def __init__(self):
        self.id = DOCUMENT_ID
        self.workspace_id = WORKSPACE_ID
        self.filename = "example.com (Web)"
        self.file_type = "url"
        self.source_url = "https://example.com/article"
        self.status = "failed"
        self.error_message = "previous fetch failed"
        self.idempotency_key = None
        self.created_at = datetime.now(timezone.utc)
        self.embedding_model = "existing-model"


class _Query:
    def __init__(self, session, model):
        self.session = session
        self.model = model

    def filter(self, *args, **kwargs):
        return self

    def first(self):
        if self.model is Document:
            return self.session.doc
        return None

    def delete(self):
        self.session.delete_calls += 1
        deleted = len(self.session.chunks)
        self.session.chunks.clear()
        return deleted


class MemorySession:
    def __init__(self, doc, chunks):
        self.doc = doc
        self.chunks = list(chunks)
        self.delete_calls = 0
        self.added = []
        self._snapshot()

    def _snapshot(self):
        self._chunks = list(self.chunks)
        self._status = self.doc.status
        self._error = self.doc.error_message
        self._filename = self.doc.filename
        self._source_url = self.doc.source_url
        self._embedding_model = self.doc.embedding_model

    def query(self, model):
        return _Query(self, model)

    def add(self, obj):
        self.added.append(obj)
        self.chunks.append(obj)

    def flush(self):
        return None

    def commit(self):
        self._snapshot()

    def rollback(self):
        self.chunks[:] = list(self._chunks)
        self.doc.status = self._status
        self.doc.error_message = self._error
        self.doc.filename = self._filename
        self.doc.source_url = self._source_url
        self.doc.embedding_model = self._embedding_model
        self.added.clear()

    def refresh(self, obj):
        return None


def _app(db) -> FastAPI:
    app = FastAPI()

    @app.middleware("http")
    async def inject_user(request: Request, call_next):
        request.state.user = {"sub": OWNER}
        return await call_next(request)

    app.dependency_overrides[get_db] = lambda: db
    app.include_router(router, prefix="/api/v1")
    return app


class RetryAtomicityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.original = SimpleNamespace(
            id=uuid.uuid4(),
            document_id=DOCUMENT_ID,
            content="original indexed chunk",
            chunk_index=0,
        )
        self.doc = FakeDoc()
        self.db = MemorySession(self.doc, [self.original])

    def test_pipeline_does_not_delete_chunks_before_embed_succeeds(self) -> None:
        pipeline = DocumentPipeline(self.db)
        with patch.object(
            DocumentPipeline,
            "_parse",
            return_value=[{"page_number": 1, "content": "replacement text for retry"}],
        ), patch.object(
            DocumentPipeline,
            "generate_embeddings_with_retry",
            new_callable=AsyncMock,
            side_effect=RuntimeError("embedding unavailable"),
        ):
            with self.assertRaises(RuntimeError):
                asyncio.run(
                    pipeline.run_ingestion_for_document(
                        self.doc,
                        b"<html>new</html>",
                        "url",
                    )
                )
        self.assertEqual(self.db.delete_calls, 0)
        self.assertEqual(len(self.db.chunks), 1)
        self.assertEqual(self.db.chunks[0].content, "original indexed chunk")

    def test_sync_retry_keeps_original_chunks_when_embed_fails(self) -> None:
        client = TestClient(_app(self.db))
        with patch("app.api.endpoints._get_owned_document", return_value=self.doc), \
             patch(
                 "app.api.endpoints._download_public_html",
                 new_callable=AsyncMock,
                 return_value=b"<html>replacement</html>",
             ), \
             patch("app.api.endpoints.redis_healthy", return_value=False), \
             patch.object(
                 DocumentPipeline,
                 "_parse",
                 return_value=[{"page_number": 1, "content": "replacement text for retry"}],
             ), \
             patch.object(
                 DocumentPipeline,
                 "generate_embeddings_with_retry",
                 new_callable=AsyncMock,
                 side_effect=RuntimeError("embedding unavailable"),
             ):
            response = client.post(
                f"/api/v1/documents/{self.doc.id}/retry",
                json={"language": "auto"},
                headers={"X-Test-User": OWNER, "Idempotency-Key": "retry-atomic"},
            )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.doc.status, "failed")
        self.assertEqual(len(self.db.chunks), 1)
        self.assertEqual(self.db.chunks[0].content, "original indexed chunk")
        self.assertEqual(self.db.chunks[0].id, self.original.id)


if __name__ == "__main__":
    unittest.main()
