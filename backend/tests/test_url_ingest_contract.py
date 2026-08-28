"""Contract tests for website/YouTube ingest routes and non-destructive retry."""

from __future__ import annotations

import os
import sys
import unittest
import uuid
from datetime import datetime, timezone
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

from fastapi import FastAPI, HTTPException, Request
from fastapi.testclient import TestClient

from app.api.endpoints import router
from app.core.database import get_db
from app.services.transcription_language import normalize_transcription_language


OWNER = "owner-1"
OTHER = "other-user"
WORKSPACE_ID = uuid.uuid4()
DOCUMENT_ID = uuid.uuid4()


class FakeDoc:
    def __init__(self, **kwargs):
        self.id = kwargs.get("id", DOCUMENT_ID)
        self.workspace_id = kwargs.get("workspace_id", WORKSPACE_ID)
        self.filename = kwargs.get("filename", "example.com (Web)")
        self.file_type = kwargs.get("file_type", "url")
        self.source_url = kwargs.get("source_url", "https://example.com/article")
        self.status = kwargs.get("status", "failed")
        self.error_message = kwargs.get("error_message", "previous fetch failed")
        self.idempotency_key = kwargs.get("idempotency_key")
        self.created_at = kwargs.get("created_at", datetime.now(timezone.utc))


class FakeWorkspace:
    def __init__(self, workspace_id=WORKSPACE_ID, user_id=OWNER):
        self.id = workspace_id
        self.user_id = user_id
        self.name = "Notebook"


class FakeSession:
    def __init__(self, session_id=None, workspace_id=WORKSPACE_ID):
        self.id = session_id or uuid.uuid4()
        self.workspace_id = workspace_id
        self.title = "Ask Atlas"
        self.created_at = datetime.now(timezone.utc)
        self.messages = []


def _app() -> FastAPI:
    app = FastAPI()

    @app.middleware("http")
    async def inject_user(request: Request, call_next):
        header = request.headers.get("X-Test-User", OWNER)
        request.state.user = None if header == "anon" else {"sub": header}
        return await call_next(request)

    app.dependency_overrides[get_db] = lambda: MagicMock()
    app.include_router(router, prefix="/api/v1")
    return app


def _client() -> TestClient:
    return TestClient(_app())


class TranscriptionLanguageTests(unittest.TestCase):
    def test_auto_language_normalizes_to_none(self) -> None:
        self.assertIsNone(normalize_transcription_language("auto"))
        self.assertIsNone(normalize_transcription_language("detect"))
        self.assertIsNone(normalize_transcription_language(None))

    def test_language_tags_are_normalized(self) -> None:
        self.assertEqual(normalize_transcription_language("de"), "de")
        self.assertEqual(normalize_transcription_language("pt-BR"), "pt-br")

    def test_invalid_language_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            normalize_transcription_language("not a language")


class UrlYoutubeIngestRouteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = _client()
        self.doc = FakeDoc(status="processing", error_message=None)

    def _headers(self, user: str = OWNER, idem: str | None = "idem-1") -> dict[str, str]:
        headers = {"X-Test-User": user}
        if idem:
            headers["Idempotency-Key"] = idem
        return headers

    def test_website_ingest_posts_url_shape_and_idempotency(self) -> None:
        with patch("app.api.endpoints._get_owned_workspace", return_value=FakeWorkspace()), \
             patch("app.api.endpoints._existing_idempotent_document", return_value=None), \
             patch("app.api.endpoints._download_public_html", new_callable=AsyncMock, return_value=b"<html>ok</html>"), \
             patch("app.api.endpoints.redis_healthy", return_value=True), \
             patch("app.api.endpoints.enqueue_ingestion_job") as enqueue, \
             patch("app.api.endpoints.DocumentPipeline") as pipeline_cls:
            pipeline_cls.return_value.create_pending_document.return_value = self.doc
            response = self.client.post(
                f"/api/v1/workspaces/{WORKSPACE_ID}/documents/url",
                json={"url": "example.com/article"},
                headers=self._headers(),
            )
        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json()["id"], str(self.doc.id))
        enqueue.assert_called_once()
        kwargs = enqueue.call_args.kwargs
        self.assertEqual(kwargs["file_type"], "url")
        self.assertEqual(kwargs["source_url"], "https://example.com/article")
        self.assertNotIn("language", kwargs["source_url"])

    def test_youtube_ingest_includes_language_and_does_not_use_text_route(self) -> None:
        with patch("app.api.endpoints._get_owned_workspace", return_value=FakeWorkspace()), \
             patch("app.api.endpoints._existing_idempotent_document", return_value=None), \
             patch(
                 "app.api.endpoints._youtube_ingest_payload",
                 new_callable=AsyncMock,
                 return_value={
                     "filename": "Talk (YouTube)",
                     "file_bytes": b"# transcript",
                     "canonical_url": "https://www.youtube.com/watch?v=jNQXAC9IVRw",
                     "language": "de",
                 },
             ), \
             patch("app.api.endpoints.redis_healthy", return_value=True), \
             patch("app.api.endpoints.enqueue_ingestion_job") as enqueue, \
             patch("app.api.endpoints.DocumentPipeline") as pipeline_cls:
            pipeline_cls.return_value.create_pending_document.return_value = FakeDoc(
                file_type="youtube",
                source_url="https://www.youtube.com/watch?v=jNQXAC9IVRw",
                status="processing",
                error_message=None,
            )
            response = self.client.post(
                f"/api/v1/workspaces/{WORKSPACE_ID}/documents/youtube",
                json={"url": "https://youtu.be/jNQXAC9IVRw", "language": "de"},
                headers=self._headers(idem="yt-1"),
            )
        self.assertEqual(response.status_code, 202)
        self.assertEqual(enqueue.call_args.kwargs["language"], "de")
        self.assertEqual(
            enqueue.call_args.kwargs["source_url"],
            "https://www.youtube.com/watch?v=jNQXAC9IVRw",
        )

    def test_idempotent_replay_returns_existing_document(self) -> None:
        existing = FakeDoc(status="ready", error_message=None)
        with patch("app.api.endpoints._get_owned_workspace", return_value=FakeWorkspace()), \
             patch("app.api.endpoints._existing_idempotent_document", return_value=existing), \
             patch("app.api.endpoints._download_public_html", new_callable=AsyncMock) as download:
            response = self.client.post(
                f"/api/v1/workspaces/{WORKSPACE_ID}/documents/url",
                json={"url": "https://example.com/article"},
                headers=self._headers(),
            )
        self.assertIn(response.status_code, {200, 201})
        self.assertEqual(response.json()["id"], str(existing.id))
        download.assert_not_called()

    def test_cross_workspace_ingest_is_denied(self) -> None:
        with patch(
            "app.api.endpoints._get_owned_workspace",
            side_effect=HTTPException(status_code=404, detail="Workspace not found"),
        ):
            response = self.client.post(
                f"/api/v1/workspaces/{WORKSPACE_ID}/documents/url",
                json={"url": "https://example.com/article"},
                headers=self._headers(user=OTHER),
            )
        self.assertEqual(response.status_code, 404)

    def test_unreachable_url_returns_actionable_error(self) -> None:
        with patch("app.api.endpoints._get_owned_workspace", return_value=FakeWorkspace()), \
             patch("app.api.endpoints._existing_idempotent_document", return_value=None), \
             patch(
                 "app.api.endpoints._download_public_html",
                 new_callable=AsyncMock,
                 side_effect=HTTPException(
                     status_code=400,
                     detail="AtlasLM could not reach that URL. Check the address and try again.",
                 ),
             ):
            response = self.client.post(
                f"/api/v1/workspaces/{WORKSPACE_ID}/documents/url",
                json={"url": "https://example.com/missing"},
                headers=self._headers(),
            )
        self.assertEqual(response.status_code, 400)
        self.assertIn("could not reach that URL", response.json()["detail"])

    def test_unauthenticated_ingest_is_rejected(self) -> None:
        response = self.client.post(
            f"/api/v1/workspaces/{WORKSPACE_ID}/documents/url",
            json={"url": "https://example.com/article"},
            headers=self._headers(user="anon", idem=None),
        )
        self.assertEqual(response.status_code, 401)

    def test_private_literal_urls_are_rejected_without_fetching(self) -> None:
        urls = [
            "http://127.0.0.1/",
            "http://localhost/",
            "http://[::1]/",
            "http://10.0.0.8/internal",
            "http://172.16.1.4/",
            "http://192.168.1.20/",
            "http://169.254.169.254/latest/meta-data/",
        ]
        for url in urls:
            with self.subTest(url=url):
                with patch(
                    "app.api.endpoints._get_owned_workspace",
                    return_value=FakeWorkspace(),
                ), patch(
                    "app.api.endpoints._existing_idempotent_document",
                    return_value=None,
                ), patch(
                    "app.api.endpoints._download_public_html",
                    new_callable=AsyncMock,
                ) as download:
                    response = self.client.post(
                        f"/api/v1/workspaces/{WORKSPACE_ID}/documents/url",
                        json={"url": url},
                        headers=self._headers(),
                    )
                self.assertEqual(response.status_code, 400, url)
                download.assert_not_called()


class DocumentRetryRouteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = _client()
        self.failed = FakeDoc()

    def test_retry_success_keeps_the_same_document_id(self) -> None:
        with patch("app.api.endpoints._get_owned_document", return_value=self.failed), \
             patch("app.api.endpoints._download_public_html", new_callable=AsyncMock, return_value=b"<html>ok</html>"), \
             patch("app.api.endpoints.redis_healthy", return_value=True), \
             patch("app.api.endpoints.enqueue_ingestion_job") as enqueue:
            response = self.client.post(
                f"/api/v1/documents/{self.failed.id}/retry",
                json={"language": "auto"},
                headers={"X-Test-User": OWNER, "Idempotency-Key": "retry-1"},
            )
        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json()["id"], str(self.failed.id))
        self.assertEqual(self.failed.status, "processing")
        enqueue.assert_called_once()
        self.assertEqual(enqueue.call_args.kwargs["document_id"], self.failed.id)

    def test_retry_failure_preserves_the_failed_record(self) -> None:
        with patch("app.api.endpoints._get_owned_document", return_value=self.failed), \
             patch(
                 "app.api.endpoints._download_public_html",
                 new_callable=AsyncMock,
                 side_effect=HTTPException(status_code=400, detail="AtlasLM could not reach that URL. Check the address and try again."),
             ):
            response = self.client.post(
                f"/api/v1/documents/{self.failed.id}/retry",
                json={"language": "auto"},
                headers={"X-Test-User": OWNER, "Idempotency-Key": "retry-2"},
            )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.failed.status, "failed")
        self.assertIsNotNone(self.failed.error_message)

    def test_retry_cross_workspace_is_denied(self) -> None:
        with patch(
            "app.api.endpoints._get_owned_document",
            side_effect=HTTPException(status_code=404, detail="Document not found"),
        ):
            response = self.client.post(
                f"/api/v1/documents/{DOCUMENT_ID}/retry",
                json={"language": "auto"},
                headers={"X-Test-User": OTHER, "Idempotency-Key": "retry-3"},
            )
        self.assertEqual(response.status_code, 404)

    def test_repeated_retry_clicks_do_not_create_another_document(self) -> None:
        processing = FakeDoc(status="processing", error_message=None)
        with patch("app.api.endpoints._get_owned_document", return_value=processing), \
             patch("app.api.endpoints._download_public_html", new_callable=AsyncMock) as download, \
             patch("app.api.endpoints.enqueue_ingestion_job") as enqueue:
            first = self.client.post(
                f"/api/v1/documents/{processing.id}/retry",
                json={"language": "auto"},
                headers={"X-Test-User": OWNER, "Idempotency-Key": "retry-4"},
            )
            second = self.client.post(
                f"/api/v1/documents/{processing.id}/retry",
                json={"language": "auto"},
                headers={"X-Test-User": OWNER, "Idempotency-Key": "retry-4"},
            )
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(first.json()["id"], second.json()["id"])
        download.assert_not_called()
        enqueue.assert_not_called()


class SessionClearTests(unittest.TestCase):
    def test_clear_messages_requires_ownership(self) -> None:
        client = _client()
        session = FakeSession()
        db = MagicMock()
        app = client.app
        app.dependency_overrides[get_db] = lambda: db
        with patch("app.api.endpoints._get_owned_session", side_effect=HTTPException(status_code=404, detail="Chat session not found")):
            response = client.delete(
                f"/api/v1/sessions/{session.id}/messages",
                headers={"X-Test-User": OTHER},
            )
        self.assertEqual(response.status_code, 404)

    def test_clear_messages_deletes_rows_for_owner(self) -> None:
        client = _client()
        session = FakeSession()
        db = MagicMock()
        client.app.dependency_overrides[get_db] = lambda: db
        with patch("app.api.endpoints._get_owned_session", return_value=session):
            response = client.delete(
                f"/api/v1/sessions/{session.id}/messages",
                headers={"X-Test-User": OWNER},
            )
        self.assertEqual(response.status_code, 204)
        db.query.assert_called()
        db.commit.assert_called()


if __name__ == "__main__":
    unittest.main()
