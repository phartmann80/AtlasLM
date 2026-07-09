# backend/app/services/ingest/youtube_loader.py
"""YouTube loader -> timestamped transcript.
Strategy: try official captions first (youtube-transcript-api, no media download).
Fallback: download audio with yt-dlp and run offline Whisper (audio_loader)."""
from __future__ import annotations
from typing import List, Optional
import os
import re
import tempfile
from .base import ExtractedBlock, block
from ..transcription_language import caption_language_preferences, normalize_transcription_language

_YT_RE = re.compile(r"(?:v=|youtu\.be/|/shorts/)([A-Za-z0-9_-]{11})")


def _video_id(url: str) -> str:
    m = _YT_RE.search(url)
    if not m:
        raise ValueError("Could not parse a YouTube video id from the URL.")
    return m.group(1)


def load_youtube(url: str, language: Optional[str] = None) -> List[ExtractedBlock]:
    vid = _video_id(url)
    normalized_language = normalize_transcription_language(language)

    # 1) Captions (fast, no download)
    try:
        from youtube_transcript_api import YouTubeTranscriptApi

        preferences = caption_language_preferences(normalized_language)
        if hasattr(YouTubeTranscriptApi, "get_transcript"):
            entries = YouTubeTranscriptApi.get_transcript(vid, languages=preferences)
        else:
            transcript = YouTubeTranscriptApi().fetch(
                vid,
                languages=preferences,
                preserve_formatting=False,
            )
            entries = transcript.to_raw_data()

        blocks = [
            block(e["text"].strip(), timestamp=e["start"])
            for e in entries if e.get("text", "").strip()
        ]
        if blocks:
            return blocks
    except Exception:
        pass  # fall through to Whisper

    # 2) Whisper fallback (download audio -> offline transcription)
    from .audio_loader import transcribe_audio
    with tempfile.TemporaryDirectory() as tmp:
        out = os.path.join(tmp, "audio.%(ext)s")
        import yt_dlp
        ydl_opts = {
            "format": "bestaudio/best",
            "outtmpl": out,
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "http_headers": {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 Chrome/126.0 Safari/537.36"
                )
            },
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        # yt-dlp may append an extension; find the produced file
        produced = next((os.path.join(tmp, f) for f in os.listdir(tmp)), "")
        if not produced:
            raise ValueError("No audio file was downloaded for transcription.")
        return transcribe_audio(produced, language=normalized_language)
