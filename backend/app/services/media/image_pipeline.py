"""Image ingest: EXIF strip, OCR, vision description, dual chunk groups."""
from __future__ import annotations

import io
import logging
import os
import time
from pathlib import Path
from typing import Any, Optional

from . import (
    IMAGE_EXTENSIONS,
    IMAGE_MIME,
    MSG_IMAGE_EMPTY,
    MSG_IMAGE_TOO_LARGE,
    MSG_UNSUPPORTED_IMAGE,
    MediaIngestError,
)

logger = logging.getLogger("atlaslm.media.image")

VISION_PROMPT = (
    "Describe only what is visible. Return three labeled sections:\n"
    "1. Literal text: transcribe every readable word exactly.\n"
    "2. Chart, diagram, or table: describe the structure and list visible values.\n"
    "3. Caption: one sentence summarizing the image.\n"
    "Do not invent values that are not visible."
)


def detect_image_kind(filename: str) -> Optional[str]:
    ext = Path(filename or "").suffix.lower()
    return ext if ext in IMAGE_EXTENSIONS else None


def validate_image_upload(filename: str, data: bytes, max_mb: int = 20) -> str:
    ext = detect_image_kind(filename)
    if not ext:
        raise MediaIngestError(MSG_UNSUPPORTED_IMAGE)
    if len(data) > max_mb * 1024 * 1024:
        raise MediaIngestError(MSG_IMAGE_TOO_LARGE)
    if len(data) < 32:
        raise MediaIngestError(MSG_IMAGE_EMPTY)
    return ext


def strip_exif_and_normalize(src_path: str, dest_path: str) -> str:
    from PIL import Image

    src = Path(src_path)
    ext = src.suffix.lower()
    working = src_path
    if ext in {".heic", ".heif"}:
        from .ffmpeg import convert_heic
        converted = str(Path(dest_path).with_suffix(".converted.png"))
        convert_heic(src_path, converted)
        working = converted
    with Image.open(working) as img:
        img.load()
        mode = "RGB"
        if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
            mode = "RGBA"
        clean = Image.new(mode, img.size)
        converted_img = img.convert(mode)
        clean.putdata(list(converted_img.getdata()))
        save_path = dest_path
        if mode == "RGBA":
            save_path = str(Path(dest_path).with_suffix(".png"))
            clean.save(save_path, format="PNG")
        else:
            suffix = Path(dest_path).suffix.lower()
            fmt = "JPEG" if suffix in {".jpg", ".jpeg"} else "PNG"
            if fmt == "JPEG":
                clean = clean.convert("RGB")
            clean.save(save_path, format=fmt)
    logger.info("image_exif_stripped dest=%s", Path(save_path).name)
    return save_path


def ocr_image(path: str) -> tuple[str, Optional[str]]:
    from PIL import Image
    import pytesseract

    started = time.monotonic()
    lang = _detect_language(path)
    with Image.open(path) as img:
        kwargs: dict[str, Any] = {}
        if lang:
            kwargs["lang"] = lang
        try:
            text = pytesseract.image_to_string(img, **kwargs) or ""
        except Exception:
            text = pytesseract.image_to_string(img) or ""
            lang = None
    duration_ms = int((time.monotonic() - started) * 1000)
    logger.info("image_ocr duration_ms=%s lang=%s chars=%s", duration_ms, lang or "auto", len(text.strip()))
    return text.strip(), lang


def _detect_language(path: str) -> Optional[str]:
    try:
        import pytesseract
        from PIL import Image
        with Image.open(path) as img:
            osd = pytesseract.image_to_osd(img)
        for line in osd.splitlines():
            if line.lower().startswith("script:"):
                script = line.split(":", 1)[1].strip().lower()
                mapping = {
                    "latin": "eng",
                    "cyrillic": "rus",
                    "arabic": "ara",
                    "han": "chi_sim",
                    "hangul": "kor",
                    "japanese": "jpn",
                    "devanagari": "hin",
                }
                return mapping.get(script)
    except Exception:
        return None
    return None


def vision_describe(path: str) -> str:
    from app.core.providers import describe_visual_source

    started = time.monotonic()
    mime = IMAGE_MIME.get(Path(path).suffix.lower(), "image/png")
    data = Path(path).read_bytes()
    text = describe_visual_source(data, mime, VISION_PROMPT)
    duration_ms = int((time.monotonic() - started) * 1000)
    logger.info("image_vision duration_ms=%s chars=%s", duration_ms, len((text or "").strip()))
    return (text or "").strip()


def build_image_blocks(ocr_text: str, vision_text: str, filename: str) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    if ocr_text:
        blocks.append({
            "text": f"OCR text from image '{filename}':\n\n{ocr_text}",
            "page": 1,
            "source_kind": "image_ocr",
            "region": "full",
            "char_offset": 0,
        })
    if vision_text:
        blocks.append({
            "text": f"Visual description of image '{filename}':\n\n{vision_text}",
            "page": 1,
            "source_kind": "image_vision",
            "region": "full",
            "char_offset": 0,
        })
    if not blocks:
        raise MediaIngestError(MSG_IMAGE_EMPTY)
    return blocks


def process_image_file(src_path: str, filename: str, work_dir: str) -> tuple[list[dict[str, Any]], str]:
    dest = os.path.join(work_dir, "normalized.png")
    normalized = strip_exif_and_normalize(src_path, dest)
    ocr_text, _lang = ocr_image(normalized)
    vision_text = ""
    try:
        vision_text = vision_describe(normalized)
    except Exception:
        logger.info("image_vision_skipped filename=%s", filename)
    return build_image_blocks(ocr_text, vision_text, filename), normalized
