"""YouTube ingest: captions first, audio fallback, specific failure messages."""
from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import tempfile
from typing import Any, Optional
from urllib.parse import parse_qs, urlparse

from . import (
    MSG_YOUTUBE_AGE,
    MSG_YOUTUBE_BLOCKED,
    MSG_YOUTUBE_INVALID,
    MSG_YOUTUBE_LIVE,
    MSG_YOUTUBE_PRIVATE,
    MediaIngestError,
)

logger = logging.getLogger("atlaslm.media.youtube")

VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")
WATCH_PATTERNS = [
    r"(?:youtube\.com/watch\?(?:.*&)?v=)([A-Za-z0-9_-]{11})",
    r"(?:youtu\.be/)([A-Za-z0-9_-]{11})",
    r"(?:youtube\.com/shorts/)([A-Za-z0-9_-]{11})",
    r"(?:youtube\.com/embed/)([A-Za-z0-9_-]{11})",
    r"(?:youtube\.com/live/)([A-Za-z0-9_-]{11})",
]


def extract_video_id(url: str) -> Optional[str]:
    raw = (url or "").strip()
    if VIDEO_ID_RE.fullmatch(raw):
        return raw
    for pat in WATCH_PATTERNS:
        match = re.search(pat, raw)
        if match:
            return match.group(1)
    parsed = urlparse(raw)
    if "youtube.com" in (parsed.netloc or "") or "youtu.be" in (parsed.netloc or ""):
        qs = parse_qs(parsed.query)
        candidate = (qs.get("v") or [None])[0]
        if candidate and VIDEO_ID_RE.fullmatch(candidate):
            return candidate
    return None


def start_seconds(url: str) -> Optional[int]:
    parsed = urlparse(url or "")
    qs = parse_qs(parsed.query)
    if "t" in qs:
        return _parse_time(qs["t"][0])
    if "start" in qs:
        return _parse_time(qs["start"][0])
    if parsed.fragment.startswith("t="):
        return _parse_time(parsed.fragment[2:])
    return None


def _parse_time(value: str) -> Optional[int]:
    text = (value or "").strip()
    if text.isdigit():
        return int(text)
    if text.endswith("s") and text[:-1].isdigit():
        return int(text[:-1])
    match = re.match(r"^(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s)?$", text)
    if not match or not text:
        return None
    hours = int(match.group(1) or 0)
    minutes = int(match.group(2) or 0)
    seconds = int(match.group(3) or 0)
    if hours == minutes == seconds == 0 and not re.search(r"\d", text):
        return None
    return hours * 3600 + minutes * 60 + seconds


def canonical_url(video_id: str, start_s: Optional[int] = None) -> str:
    url = f"https://www.youtube.com/watch?v={video_id}"
    if start_s and start_s > 0:
        url += f"&t={int(start_s)}"
    return url


def fetch_captions(video_id: str, language: Optional[str] = None) -> list[dict[str, Any]]:
    from youtube_transcript_api import YouTubeTranscriptApi
    from app.services.transcription_language import caption_language_preferences, normalize_transcription_language

    normalized = None
    if language:
        try:
            normalized = normalize_transcription_language(language)
        except ValueError:
            normalized = None
    preferences = caption_language_preferences(normalized)
    try:
        if hasattr(YouTubeTranscriptApi, "get_transcript"):
            entries = YouTubeTranscriptApi.get_transcript(video_id, languages=preferences)
        else:
            transcript = YouTubeTranscriptApi().fetch(
                video_id, languages=preferences, preserve_formatting=False,
            )
            entries = transcript.to_raw_data()
    except Exception as exc:
        _reraise_youtube(exc)
        return []
    cues = []
    for entry in entries:
        text = (entry.get("text") or "").strip()
        if not text:
            continue
        start = float(entry.get("start") or 0)
        duration = float(entry.get("duration") or 0)
        cues.append({
            "text": text,
            "start": start,
            "end": start + duration,
            "speaker": None,
        })
    return cues


def _reraise_youtube(exc: Exception) -> None:
    name = type(exc).__name__.lower()
    message = str(exc).lower()
    if "private" in name or "private" in message:
        raise MediaIngestError(MSG_YOUTUBE_PRIVATE) from exc
    if "age" in name or "age-restricted" in message or "confirm your age" in message:
        raise MediaIngestError(MSG_YOUTUBE_AGE) from exc
    if "live" in name or "is live" in message:
        raise MediaIngestError(MSG_YOUTUBE_LIVE) from exc
    if "bot" in message or "sign in" in message:
        raise MediaIngestError(MSG_YOUTUBE_BLOCKED) from exc
    # captions missing is not fatal; caller falls back
    return None


def dump_metadata(url: str) -> dict[str, Any]:
    ytdlp = _ytdlp_cmd()
    args = ytdlp + ["--dump-json", "--no-playlist", "--skip-download", url]
    cookies = _cookies_path()
    if cookies:
        args[1:1] = ["--cookies", cookies]
    proc = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=45, check=False)
    if proc.returncode == 0 and proc.stdout:
        try:
            return json.loads(proc.stdout.decode("utf-8", errors="replace").splitlines()[0])
        except json.JSONDecodeError:
            return {}
    err = proc.stderr.decode("utf-8", errors="replace").lower()
    _raise_from_ytdlp_text(err)
    return {}


def fetch_oembed(video_id: str) -> dict[str, Any]:
    import httpx
    watch = canonical_url(video_id)
    try:
        with httpx.Client(timeout=15.0) as client:
            response = client.get(
                "https://www.youtube.com/oembed",
                params={"url": watch, "format": "json"},
            )
        if response.status_code >= 400:
            return {}
        data = response.json()
        return {
            "title": data.get("title") or f"YouTube {video_id}",
            "channel": data.get("author_name") or "",
            "thumbnail": data.get("thumbnail_url") or "",
        }
    except Exception:
        return {}


def download_audio(url: str, dest_dir: str) -> str:
    ytdlp = _ytdlp_cmd()
    outtmpl = os.path.join(dest_dir, "audio.%(ext)s")
    args = ytdlp + [
        "-f", "bestaudio/best",
        "-x", "--audio-format", "m4a",
        "--no-playlist",
        "-o", outtmpl,
        url,
    ]
    cookies = _cookies_path()
    if cookies:
        args[1:1] = ["--cookies", cookies]
    proc = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=300, check=False)
    err = proc.stderr.decode("utf-8", errors="replace")
    if proc.returncode != 0:
        _raise_from_ytdlp_text(err.lower())
        raise MediaIngestError(MSG_YOUTUBE_BLOCKED)
    produced = next((os.path.join(dest_dir, name) for name in os.listdir(dest_dir) if name.startswith("audio.")), "")
    if not produced:
        raise MediaIngestError(MSG_YOUTUBE_BLOCKED)
    logger.info("youtube_audio_downloaded video_present=1")
    return produced


def _raise_from_ytdlp_text(err: str) -> None:
    if "private" in err:
        raise MediaIngestError(MSG_YOUTUBE_PRIVATE)
    if "age" in err or "confirm your age" in err:
        raise MediaIngestError(MSG_YOUTUBE_AGE)
    if "live event" in err or "premier" in err or "is live" in err:
        raise MediaIngestError(MSG_YOUTUBE_LIVE)
    if "sign in to confirm" in err or "not a bot" in err or "http error 429" in err:
        raise MediaIngestError(MSG_YOUTUBE_BLOCKED)


def _cookies_path() -> Optional[str]:
    from app.core.config import settings
    path = getattr(settings, "ATLAS_YTDLP_COOKIES", "") or os.getenv("ATLAS_YTDLP_COOKIES", "")
    if path and os.path.isfile(path):
        return path
    return None


def _ytdlp_cmd() -> list[str]:
    import shutil
    binary = shutil.which("yt-dlp")
    if binary:
        return [binary]
    return ["python", "-m", "yt_dlp"]


def caption_windows(cues: list[dict[str, Any]]) -> list[dict[str, Any]]:
    from .gladia import group_utterances
    labeled = []
    for cue in cues:
        labeled.append({
            "text": cue["text"],
            "start": cue["start"],
            "end": cue.get("end") or cue["start"],
            "speaker": "Captions",
        })
    windows = group_utterances(labeled)
    for window in windows:
        window["source_kind"] = "youtube"
        window["speaker"] = None
    return windows


def card_from_meta(video_id: str, meta: dict[str, Any], oembed: dict[str, Any]) -> dict[str, Any]:
    title = meta.get("title") or oembed.get("title") or f"YouTube {video_id}"
    channel = meta.get("channel") or meta.get("uploader") or oembed.get("channel") or ""
    duration = meta.get("duration")
    thumbnail = (
        meta.get("thumbnail")
        or (meta.get("thumbnails") or [{}])[-1].get("url")
        or oembed.get("thumbnail")
        or f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"
    )
    return {
        "title": title,
        "channel": channel,
        "duration": duration,
        "thumbnail": thumbnail,
        "video_id": video_id,
    }
