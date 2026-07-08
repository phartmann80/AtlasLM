# backend/app/services/ingest/youtube_loader.py
"""YouTube loader -> timestamped transcript.
Strategy: try official captions first (youtube-transcript-api, no media download).
Fallback: download audio with yt-dlp and run offline Whisper (audio_loader)."""
from __future__ import annotations
from typing import List
import os
import re
import tempfile
from .base import ExtractedBlock, block

_YT_RE = re.compile(r"(?:v=|youtu\.be/|/shorts/)([A-Za-z0-9_-]{11})")


def _video_id(url: str) -> str:
    m = _YT_RE.search(url)
    if not m:
        raise ValueError("Could not parse a YouTube video id from the URL.")
    return m.group(1)


def load_youtube(url: str) -> List[ExtractedBlock]:
    vid = _video_id(url)

    # 1) Captions (fast, no download)
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
        entries = YouTubeTranscriptApi.get_transcript(vid)
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
            "noplaylist": True,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        # yt-dlp may append an extension; find the produced file
        produced = next((os.path.join(tmp, f) for f in os.listdir(tmp)), "")
        if not produced:
            raise ValueError("No audio file was downloaded for transcription.")
        return transcribe_audio(produced)
