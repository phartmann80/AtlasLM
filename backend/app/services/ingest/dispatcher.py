# backend/app/services/ingest/dispatcher.py
"""
Routes an incoming source (file path or URL) to the correct loader, then hands
the extracted blocks to the EXISTING chunk -> embed -> pgvector pipeline.

DEV TEAM: wire `persist_blocks(...)` to your existing ingestion routine in
rag.py / ingestion service. The two TODO calls are the only integration points.
"""
from __future__ import annotations
import os
from typing import List, Optional
from .base import ExtractedBlock

from .docx_loader import load_docx
from .pptx_loader import load_pptx
from .xlsx_loader import load_spreadsheet
from .image_loader import load_image
from .audio_loader import transcribe_audio
from .youtube_loader import load_youtube

EXT_MAP = {
    ".pdf":  "pdf",     # handled by existing PyMuPDF loader
    ".docx": "docx",
    ".pptx": "pptx",
    ".xlsx": "xlsx", ".csv": "xlsx",
    ".png": "image", ".jpg": "image", ".jpeg": "image", ".webp": "image",
    ".mp3": "audio", ".wav": "audio", ".m4a": "audio", ".aac": "audio",
    ".ogg": "audio", ".flac": "audio",
}


def detect_kind(path_or_url: str) -> str:
    low = path_or_url.lower()
    if low.startswith("http"):
        if "youtube.com" in low or "youtu.be" in low:
            return "youtube"
        return "web"  # existing crawler
    return EXT_MAP.get(os.path.splitext(low)[1], "unknown")


def extract_blocks(
    kind: str,
    path_or_url: str,
    language: Optional[str] = None,
) -> List[ExtractedBlock]:
    if kind == "docx":    return load_docx(path_or_url)
    if kind == "pptx":    return load_pptx(path_or_url)
    if kind == "xlsx":    return load_spreadsheet(path_or_url)
    if kind == "image":   return load_image(path_or_url)
    if kind == "audio":   return transcribe_audio(path_or_url, language=language)
    if kind == "youtube": return load_youtube(path_or_url, language=language)
    raise ValueError(f"No Patch-003 loader for kind '{kind}'. "
                     f"(pdf/web are handled by existing loaders.)")
