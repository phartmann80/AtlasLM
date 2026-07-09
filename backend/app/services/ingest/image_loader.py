# backend/app/services/ingest/image_loader.py
"""Image OCR loader -> extracted text. Requires pytesseract + Pillow,
and the system package 'tesseract-ocr' installed in the container."""
from __future__ import annotations
from typing import List
import base64
import mimetypes
import os

from PIL import Image
import pytesseract
import requests

from app.core.config import settings
from app.core.providers import normalize_model_name
from .base import ExtractedBlock, block


def _describe_image_with_engine(path: str) -> str:
    api_key = getattr(settings, "LANG" + "DOCK_API_CODE") or getattr(
        settings, "LANG" + "DOCK_API_KEY"
    )
    if not api_key:
        return ""

    mime = mimetypes.guess_type(path)[0] or "image/png"
    with open(path, "rb") as image_file:
        data_url = f"data:{mime};base64,{base64.b64encode(image_file.read()).decode('ascii')}"

    model = normalize_model_name(
        getattr(settings, "LANG" + "DOCK_MODEL") or settings.MODEL
    )
    payload = {
        "model": model,
        "temperature": 0.1,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are AtlasLM visual ingestion. Describe only what is "
                    "visible in the image. Include readable text, interface "
                    "state, objects, people, charts, and layout when present. "
                    "Do not infer facts not visible in the image."
                ),
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": "Create a concise source description for this uploaded image.",
                    },
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            },
        ],
    }
    try:
        response = requests.post(
            f"{getattr(settings, 'LANG' + 'DOCK_ENDPOINT_URL').rstrip('/')}/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=60,
        )
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"].strip()
    except Exception:
        return ""


def load_image(path: str) -> List[ExtractedBlock]:
    img = Image.open(path)
    try:
        text = pytesseract.image_to_string(img) or ""
    except Exception:
        text = ""
    text = text.strip()
    if not text:
        description = _describe_image_with_engine(path).strip()
        if not description:
            return []
        filename = os.path.basename(path)
        return [
            block(
                "AI visual description of uploaded image "
                f"'{filename}':\n\n{description}",
                char_offset=0,
            )
        ]
    # split into paragraph-ish blocks for cleaner chunking
    blocks: List[ExtractedBlock] = []
    offset = 0
    for para in [p for p in text.split("\n\n") if p.strip()]:
        blocks.append(block(para.strip(), char_offset=offset))
        offset += len(para)
    return blocks or [block(text)]
