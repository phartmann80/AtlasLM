"""On-disk storage for uploaded sources and generated Studio files."""
from __future__ import annotations

import os
import uuid
from pathlib import Path
from typing import Optional

from app.core.config import settings


def media_root() -> Path:
    root = Path(getattr(settings, "ATLAS_MEDIA_DIR", None) or os.getenv("ATLAS_MEDIA_DIR", "/data/media"))
    root.mkdir(parents=True, exist_ok=True)
    return root


def audio_root() -> Path:
    root = Path(os.getenv("AUDIO_DIR", "/data/audio"))
    root.mkdir(parents=True, exist_ok=True)
    return root


def document_dir(workspace_id: uuid.UUID, document_id: uuid.UUID) -> Path:
    path = media_root() / str(workspace_id) / str(document_id)
    path.mkdir(parents=True, exist_ok=True)
    return path


def write_bytes(path: Path, data: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def save_source_file(
    workspace_id: uuid.UUID,
    document_id: uuid.UUID,
    filename: str,
    data: bytes,
) -> str:
    safe_name = Path(filename).name or "source.bin"
    dest = document_dir(workspace_id, document_id) / safe_name
    write_bytes(dest, data)
    return str(dest)


def save_source_path(
    workspace_id: uuid.UUID,
    document_id: uuid.UUID,
    filename: str,
    src_path: str,
) -> str:
    import shutil
    safe_name = Path(filename).name or "source.bin"
    dest = document_dir(workspace_id, document_id) / safe_name
    dest.parent.mkdir(parents=True, exist_ok=True)
    if os.path.abspath(src_path) != os.path.abspath(dest):
        shutil.copyfile(src_path, dest)
    return str(dest)


def save_generated(kind: str, file_id: str, filename: str, data: bytes) -> str:
    dest = audio_root() / kind / file_id / filename
    write_bytes(dest, data)
    return str(dest)


def resolve_existing(path: Optional[str]) -> Optional[str]:
    if not path:
        return None
    return path if os.path.exists(path) else None
