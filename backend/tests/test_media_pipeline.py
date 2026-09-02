"""Unit and recorded-fixture tests for media ingest and Studio generation."""

from __future__ import annotations

import json
import os
import sys
import unittest
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

os.environ.setdefault("JWT_SECRET", "test-jwt-secret")
os.environ.setdefault("DATABASE_URL", "postgresql://atlaslm@localhost:5435/atlaslm_db")

for _name in (
    "fitz",
    "faster_whisper",
    "yt_dlp",
    "youtube_transcript_api",
    "pytesseract",
    "PIL",
    "PIL.Image",
    "docx",
    "openpyxl",
    "pptx",
    "bs4",
    "lxml",
    "pandas",
    "reportlab",
    "cryptography",
    "kokoro_onnx",
    "onnxruntime",
    "soundfile",
    "numpy",
):
    sys.modules.setdefault(_name, MagicMock())

from app.services.media import (
    MSG_IMAGE_EMPTY,
    MSG_IMAGE_TOO_LARGE,
    MSG_NOT_MEDIA,
    MSG_UNSUPPORTED_IMAGE,
    MSG_YOUTUBE_BLOCKED,
    MSG_YOUTUBE_INVALID,
    MSG_YOUTUBE_PRIVATE,
    MediaIngestError,
)
from app.services.media import gladia
from app.services.media import image_pipeline
from app.services.media import jobs as jobstore
from app.services.media import youtube as youtube_mod
from app.services.media.ingest_api import classify_filename, validate_and_stage_file
from app.services.studio_gen.svg_templates import render_infographic_svg
from app.services.tts import TTSProvider
from app.services.tts.kokoro import KokoroTTSProvider, get_tts_provider

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "gladia_done.json"


class ImageValidateTests(unittest.TestCase):
    def test_unsupported_type(self) -> None:
        with self.assertRaises(MediaIngestError) as ctx:
            image_pipeline.validate_image_upload("notes.gif", b"x" * 100)
        self.assertEqual(str(ctx.exception), MSG_UNSUPPORTED_IMAGE)

    def test_too_large(self) -> None:
        with self.assertRaises(MediaIngestError) as ctx:
            image_pipeline.validate_image_upload("chart.png", b"x" * (21 * 1024 * 1024))
        self.assertEqual(str(ctx.exception), MSG_IMAGE_TOO_LARGE)

    def test_empty(self) -> None:
        with self.assertRaises(MediaIngestError) as ctx:
            image_pipeline.validate_image_upload("blank.png", b"short")
        self.assertEqual(str(ctx.exception), MSG_IMAGE_EMPTY)

    def test_build_dual_chunk_groups(self) -> None:
        blocks = image_pipeline.build_image_blocks("Revenue 12", "A bar chart of revenue.", "chart.png")
        kinds = {b["source_kind"] for b in blocks}
        self.assertEqual(kinds, {"image_ocr", "image_vision"})
        self.assertTrue(all(b["region"] == "full" for b in blocks))

    def test_empty_ocr_and_vision_fails(self) -> None:
        with self.assertRaises(MediaIngestError) as ctx:
            image_pipeline.build_image_blocks("", "", "blank.png")
        self.assertEqual(str(ctx.exception), MSG_IMAGE_EMPTY)


class IngestClassifyTests(unittest.TestCase):
    def test_classify(self) -> None:
        self.assertEqual(classify_filename("a.PNG"), "image")
        self.assertEqual(classify_filename("talk.mp3"), "audio")
        self.assertEqual(classify_filename("clip.mp4"), "video")
        self.assertIsNone(classify_filename("notes.pdf"))

    def test_fake_mp4_rejected_before_job(self) -> None:
        with patch("app.services.media.ingest_api.ffmpeg_mod.probe", side_effect=MediaIngestError(MSG_NOT_MEDIA)):
            with self.assertRaises(MediaIngestError) as ctx:
                validate_and_stage_file("movie.mp4", b"%PDF-1.4 fake media renamed")
        self.assertEqual(str(ctx.exception), MSG_NOT_MEDIA)


class GladiaFixtureTests(unittest.TestCase):
    def setUp(self) -> None:
        self.payload = json.loads(FIXTURE.read_text(encoding="utf-8"))

    def test_extract_utterances_from_recorded_response(self) -> None:
        utterances = gladia.extract_utterances(self.payload)
        self.assertEqual(len(utterances), 4)
        self.assertEqual(utterances[0]["speaker"], "Speaker 1")
        self.assertEqual(utterances[1]["speaker"], "Speaker 2")
        self.assertIn("12 million", utterances[1]["text"])

    def test_group_windows_60_to_90s(self) -> None:
        windows = gladia.group_utterances(gladia.extract_utterances(self.payload))
        self.assertGreaterEqual(len(windows), 2)
        for window in windows:
            span = (window["end_ms"] - window["start_ms"]) / 1000.0
            self.assertLessEqual(span, 90.5)
            self.assertIn("start_ms", window)
            self.assertIn("speaker", window)

    def test_event_only_payload_has_no_utterances(self) -> None:
        from app.services.media.runner import _transcription_ready
        self.assertFalse(_transcription_ready({"id": "rec-fixture-1", "event": "transcription.success"}))
        self.assertTrue(_transcription_ready(self.payload))


class YouTubeTests(unittest.TestCase):
    def test_watch_short_and_be_ids(self) -> None:
        self.assertEqual(youtube_mod.extract_video_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ"), "dQw4w9WgXcQ")
        self.assertEqual(youtube_mod.extract_video_id("https://youtu.be/dQw4w9WgXcQ?t=12"), "dQw4w9WgXcQ")
        self.assertEqual(youtube_mod.extract_video_id("https://www.youtube.com/shorts/dQw4w9WgXcQ"), "dQw4w9WgXcQ")
        self.assertEqual(youtube_mod.start_seconds("https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=1m5s"), 65)
        self.assertEqual(
            youtube_mod.canonical_url("dQw4w9WgXcQ", 12),
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=12",
        )

    def test_invalid_url(self) -> None:
        self.assertIsNone(youtube_mod.extract_video_id("https://vimeo.com/123"))

    def test_private_and_blocked_messages(self) -> None:
        with self.assertRaises(MediaIngestError) as ctx:
            youtube_mod._raise_from_ytdlp_text("this video is private")
        self.assertEqual(str(ctx.exception), MSG_YOUTUBE_PRIVATE)
        with self.assertRaises(MediaIngestError) as ctx:
            youtube_mod._raise_from_ytdlp_text("sign in to confirm you're not a bot")
        self.assertEqual(str(ctx.exception), MSG_YOUTUBE_BLOCKED)

    def test_invalid_message_constant(self) -> None:
        self.assertIn("youtube.com/watch", MSG_YOUTUBE_INVALID)


class JobStoreTests(unittest.TestCase):
    def test_fail_retries_then_exhausts(self) -> None:
        db = MagicMock()
        job = SimpleNamespace(
            retry_count=0,
            max_retries=2,
            status="processing",
            stage="ffmpeg",
            failure_reason=None,
            started_at=datetime.now(timezone.utc),
            created_at=datetime.now(timezone.utc),
            finished_at=None,
            updated_at=None,
            last_heartbeat_at=None,
            id=uuid.uuid4(),
            kind="audio_ingest",
        )
        jobstore.fail(db, job, "temporary")
        self.assertEqual(job.status, "queued")
        self.assertEqual(job.retry_count, 1)
        jobstore.fail(db, job, "temporary")
        self.assertEqual(job.retry_count, 2)
        self.assertEqual(job.status, "queued")
        jobstore.fail(db, job, "temporary")
        self.assertEqual(job.status, "failed")
        self.assertEqual(job.failure_reason, "temporary")

    def test_callback_url_embeds_token(self) -> None:
        job = SimpleNamespace(callback_token="tok_secret_value")
        with patch("app.services.media.jobs.settings") as settings:
            settings.GLADIA_CALLBACK_BASE = "https://api.staging.atlaslm.cloud"
            url = jobstore.callback_url(job)
        self.assertTrue(url.endswith("token=tok_secret_value"))
        self.assertIn("/api/v1/internal/media/stt-callback", url)

    def test_reaper_fails_stale_processing(self) -> None:
        stale = SimpleNamespace(
            status="processing",
            last_heartbeat_at=datetime.now(timezone.utc) - timedelta(hours=2),
            updated_at=None,
            created_at=datetime.now(timezone.utc) - timedelta(hours=2),
            retry_count=2,
            max_retries=2,
            failure_reason=None,
            stage="ffmpeg",
            finished_at=None,
            started_at=None,
            id=uuid.uuid4(),
            kind="audio_ingest",
        )
        db = MagicMock()
        query = db.query.return_value
        query.filter.return_value.all.return_value = [stale]
        changed = jobstore.reap_stale(db)
        self.assertEqual(changed, 1)
        self.assertEqual(stale.status, "failed")

    def test_concurrency_message(self) -> None:
        db = MagicMock()
        db.query.return_value.filter.return_value.count.return_value = 2
        with self.assertRaises(MediaIngestError) as ctx:
            jobstore.assert_concurrency(db, "user-1")
        self.assertIn("two media jobs", str(ctx.exception))


class TTSInterfaceTests(unittest.TestCase):
    def test_provider_contract(self) -> None:
        self.assertTrue(issubclass(KokoroTTSProvider, TTSProvider))
        provider = get_tts_provider()
        wav = provider.synthesize("", "af_heart")
        self.assertGreater(len(wav), 44)
        self.assertEqual(wav[:4], b"RIFF")


class InfographicSvgTests(unittest.TestCase):
    def test_facts_template_uses_brand_palette(self) -> None:
        svg = render_infographic_svg({
            "headline": "Quarterly results",
            "kicker": "From notebook sources",
            "facts": [
                {"label": "Revenue", "value": "12 million", "cite": "S1"},
                {"label": "Growth", "value": "33%", "cite": "S2"},
                {"label": "Headcount", "value": "48", "cite": "S1"},
            ],
        })
        self.assertIn("#0b1220", svg)
        self.assertIn("#7c6bb5", svg)
        self.assertNotIn("#ff3b00", svg.lower())
        self.assertIn("12 million", svg)
        self.assertIn('viewBox="0 0 1200 1500"', svg)


class MediaIngestIntegrationTests(unittest.TestCase):
    """WP1-WP3 path against recorded Gladia JSON. No live HTTP."""

    def test_recorded_stt_to_windows(self) -> None:
        payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
        utterances = gladia.extract_utterances(payload)
        windows = gladia.group_utterances(utterances)
        self.assertTrue(windows)
        first = windows[0]
        self.assertIn("Speaker", first["speaker"])
        self.assertIsInstance(first["start_ms"], int)
        duration = payload["result"]["metadata"]["audio_duration"]
        self.assertGreater(duration, 0)

    def test_youtube_caption_windows_keep_timestamps(self) -> None:
        cues = [
            {"text": "Hello", "start": 0.0, "end": 2.0},
            {"text": "world", "start": 2.0, "end": 4.0},
            {"text": "later", "start": 70.0, "end": 72.0},
        ]
        windows = youtube_mod.caption_windows(cues)
        self.assertGreaterEqual(len(windows), 1)
        self.assertEqual(windows[0]["source_kind"], "youtube")
        self.assertEqual(windows[0]["start_ms"], 0)


if __name__ == "__main__":
    unittest.main()
