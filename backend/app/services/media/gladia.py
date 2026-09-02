"""Gladia pre-recorded speech-to-text client.

Uses POST /v2/upload then POST /v2/pre-recorded with diarization and a
per-job callback token. Polling is the fallback. Never logs transcripts.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Optional

import httpx

from app.core.config import settings
from . import MSG_GLADIA_MISSING, MSG_GLADIA_TIMEOUT, MediaIngestError

logger = logging.getLogger("atlaslm.media.stt")

POLL_INTERVAL_S = 15
POLL_MAX_S = 60 * 60


def _base() -> str:
    return (settings.GLADIA_BASE_URL or "https://api.gladia.io").rstrip("/")


def _headers() -> dict[str, str]:
    key = settings.GLADIA_API_KEY or ""
    if not key:
        raise MediaIngestError(MSG_GLADIA_MISSING)
    return {"x-gladia-key": key}


def upload_audio(path: str) -> dict[str, Any]:
    started = time.monotonic()
    with open(path, "rb") as handle:
        files = {"audio": (os_basename(path), handle, "audio/flac")}
        with httpx.Client(timeout=120.0) as client:
            response = client.post(f"{_base()}/v2/upload", headers=_headers(), files=files)
    duration_ms = int((time.monotonic() - started) * 1000)
    if response.status_code >= 400:
        logger.info("stt_upload_failed status=%s duration_ms=%s", response.status_code, duration_ms)
        raise MediaIngestError(
            "Atlas could not upload this recording for transcription. Try again in a few minutes."
        )
    data = response.json()
    audio_duration = ((data.get("audio_metadata") or {}).get("audio_duration"))
    logger.info(
        "stt_upload duration_ms=%s audio_duration=%s",
        duration_ms,
        audio_duration,
    )
    return data


def os_basename(path: str) -> str:
    import os
    return os.path.basename(path)


def start_transcription(audio_url: str, callback_url: Optional[str] = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "audio_url": audio_url,
        "diarization": True,
        "language_config": {"languages": [], "code_switching": False},
    }
    if callback_url:
        payload["callback"] = True
        payload["callback_config"] = {"url": callback_url, "method": "POST"}
    with httpx.Client(timeout=60.0) as client:
        response = client.post(
            f"{_base()}/v2/pre-recorded",
            headers={**_headers(), "Content-Type": "application/json"},
            json=payload,
        )
    if response.status_code >= 400:
        logger.info("stt_start_failed status=%s", response.status_code)
        raise MediaIngestError(
            "Atlas could not start transcription for this recording. Try again."
        )
    data = response.json()
    logger.info("stt_started provider_job_id=%s", data.get("id"))
    return data


def get_transcription(job_id: str) -> dict[str, Any]:
    with httpx.Client(timeout=60.0) as client:
        response = client.get(f"{_base()}/v2/pre-recorded/{job_id}", headers=_headers())
    if response.status_code >= 400:
        raise MediaIngestError("Atlas could not read the transcription status. Try again.")
    return response.json()


def poll_until_done(job_id: str, timeout_s: int = POLL_MAX_S) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        data = get_transcription(job_id)
        status = (data.get("status") or "").lower()
        if status in {"done", "success", "completed"}:
            audio_duration = _audio_duration(data)
            logger.info("stt_done provider_job_id=%s audio_duration=%s", job_id, audio_duration)
            return data
        if status in {"error", "failed"}:
            raise MediaIngestError(
                "Transcription failed for this recording. Try a different file or try again."
            )
        time.sleep(POLL_INTERVAL_S)
    raise MediaIngestError(MSG_GLADIA_TIMEOUT)


def _audio_duration(payload: dict[str, Any]) -> Optional[float]:
    result = payload.get("result") or payload
    meta = result.get("metadata") or {}
    return meta.get("audio_duration")


def extract_utterances(payload: dict[str, Any]) -> list[dict[str, Any]]:
    result = payload.get("result") or payload
    transcription = result.get("transcription") or {}
    raw = transcription.get("utterances") or transcription.get("segments") or []
    utterances: list[dict[str, Any]] = []
    for item in raw:
        text = (item.get("text") or "").strip()
        if not text:
            continue
        start = float(item.get("start") or 0)
        end = float(item.get("end") or start)
        speaker = item.get("speaker")
        if speaker is None:
            speaker = item.get("speaker_id")
        utterances.append({
            "text": text,
            "start": start,
            "end": end,
            "speaker": _speaker_label(speaker),
        })
    if not utterances:
        full = (transcription.get("full_transcript") or "").strip()
        if full:
            utterances.append({
                "text": full,
                "start": 0.0,
                "end": float(_audio_duration(payload) or 0),
                "speaker": "Speaker 1",
            })
    return utterances


def _speaker_label(value: Any) -> str:
    if value is None or value == "":
        return "Speaker 1"
    if isinstance(value, int):
        return f"Speaker {value + 1}"
    text = str(value)
    if text.isdigit():
        return f"Speaker {int(text) + 1}"
    if text.lower().startswith("speaker"):
        return text
    return f"Speaker {text}"


def group_utterances(utterances: list[dict[str, Any]], min_s: float = 60.0, max_s: float = 90.0) -> list[dict[str, Any]]:
    windows: list[dict[str, Any]] = []
    bucket: list[dict[str, Any]] = []
    bucket_start: Optional[float] = None
    for utt in utterances:
        if not bucket:
            bucket = [utt]
            bucket_start = float(utt["start"])
            continue
        proposed_end = float(utt["end"])
        span = proposed_end - float(bucket_start or 0)
        if span <= max_s:
            bucket.append(utt)
            if span >= min_s:
                windows.append(_window(bucket))
                bucket = []
                bucket_start = None
            continue
        if bucket:
            windows.append(_window(bucket))
        bucket = [utt]
        bucket_start = float(utt["start"])
    if bucket:
        windows.append(_window(bucket))
    return windows


def _window(bucket: list[dict[str, Any]]) -> dict[str, Any]:
    start = float(bucket[0]["start"])
    end = float(bucket[-1]["end"])
    speakers = []
    seen = set()
    lines = []
    for utt in bucket:
        label = utt["speaker"]
        if label not in seen:
            seen.add(label)
            speakers.append(label)
        lines.append(f"{label}: {utt['text']}")
    return {
        "text": "\n".join(lines),
        "start": start,
        "end": end,
        "start_ms": int(round(start * 1000)),
        "end_ms": int(round(end * 1000)),
        "speaker": ", ".join(speakers) if speakers else "Speaker 1",
        "timestamp": start,
        "source_kind": "audio",
    }
