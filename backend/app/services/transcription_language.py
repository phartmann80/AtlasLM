"""Shared helpers for user-selected transcription languages."""
from __future__ import annotations

import re
from typing import Optional

_LANGUAGE_RE = re.compile(r"^[a-z]{2,3}(?:-[a-z0-9]{2,8}){0,2}$")


def normalize_transcription_language(language: Optional[str]) -> Optional[str]:
    """Return a normalized language tag or None for auto-detect.

    The API accepts common BCP-47-ish tags such as "en", "de", "pt-BR",
    and "zh-CN". We intentionally keep this permissive so Android and web
    clients are not locked to a short hardcoded list.
    """
    if language is None:
        return None

    normalized = language.strip().replace("_", "-").lower()
    if normalized in ("", "auto", "detect", "auto-detect"):
        return None

    if not _LANGUAGE_RE.fullmatch(normalized):
        raise ValueError(
            "Language must be 'auto' or a language code like en, de, es, pt-BR, or zh-CN."
        )

    return normalized


def caption_language_preferences(language: Optional[str]) -> tuple[str, ...]:
    normalized = normalize_transcription_language(language)
    if not normalized:
        return ("en", "en-US", "en-GB")

    parts = normalized.split("-")
    primary = parts[0]
    preferences = [normalized]
    if primary not in preferences:
        preferences.append(primary)
    return tuple(preferences)
