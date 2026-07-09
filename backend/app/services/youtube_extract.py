"""
AtlasLM YouTube transcript extraction (Patch 006).

Given a YouTube URL, fetches the video's caption track (manual captions
preferred, auto-generated fallback) and converts it into timestamped,
citable text sections.

Design notes:
- Zero API key required. Uses YouTube's public watch page + timedtext
  endpoint, the same data the youtube-transcript-api library consumes.
- Output is sectioned into ~60-second blocks labelled with their start
  timestamp ("[12:34]"), so citations render as "competitor teardown
  video @ 12:34"  -  clickable later to deep-link t=754s.
- Videos with captions disabled fail with a clean, user-friendly error.
- No video/audio download. Transcript-only. (Audio file transcription is
  a separate source type with its own pipeline.)
"""

import json
import logging
import re
import html as html_lib
from typing import Any, Dict, List, Optional, Tuple
from xml.etree import ElementTree

import httpx

from .transcription_language import normalize_transcription_language

logger = logging.getLogger("atlaslm.youtube")

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

# Section length for citation granularity (seconds).
SECTION_SECONDS = 60

VIDEO_ID_PATTERNS = [
    r"(?:youtube\.com/watch\?(?:.*&)?v=)([A-Za-z0-9_-]{11})",
    r"(?:youtu\.be/)([A-Za-z0-9_-]{11})",
    r"(?:youtube\.com/shorts/)([A-Za-z0-9_-]{11})",
    r"(?:youtube\.com/embed/)([A-Za-z0-9_-]{11})",
    r"(?:youtube\.com/live/)([A-Za-z0-9_-]{11})",
]


class YouTubeExtractError(ValueError):
    """User-facing extraction failure."""


def extract_video_id(url: str) -> Optional[str]:
    for pat in VIDEO_ID_PATTERNS:
        m = re.search(pat, url)
        if m:
            return m.group(1)
    return None


def _format_ts(seconds: float) -> str:
    s = int(seconds)
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    return f"{h}:{m:02d}:{sec:02d}" if h else f"{m}:{sec:02d}"


async def _fetch_watch_page(client: httpx.AsyncClient, video_id: str) -> str:
    res = await client.get(
        f"https://www.youtube.com/watch?v={video_id}",
        headers={"User-Agent": USER_AGENT, "Accept-Language": "en-US,en;q=0.9"},
        timeout=15.0,
        follow_redirects=True,
    )
    res.raise_for_status()
    return res.text


def _parse_player_response(watch_html: str) -> Dict[str, Any]:
    m = re.search(r"ytInitialPlayerResponse\s*=\s*(\{.+?\})\s*;", watch_html, re.DOTALL)
    if not m:
        raise YouTubeExtractError(
            "AtlasLM could not read this YouTube video. It may be private, "
            "age-restricted, or unavailable."
        )
    try:
        return json.loads(m.group(1))
    except json.JSONDecodeError:
        raise YouTubeExtractError(
            "AtlasLM could not read this YouTube video. Please try again."
        )


def _pick_caption_track(
    player: Dict[str, Any],
    language: Optional[str] = None,
) -> Tuple[str, str]:
    """Returns (baseUrl, language). Prefers requested language, then manual/English."""
    tracks = (
        player.get("captions", {})
        .get("playerCaptionsTracklistRenderer", {})
        .get("captionTracks", [])
    )
    if not tracks:
        raise YouTubeExtractError(
            "This video has no captions or transcript available, so AtlasLM "
            "cannot ingest it. Try a video with captions enabled."
        )

    normalized_language = normalize_transcription_language(language)
    requested_primary = normalized_language.split("-")[0] if normalized_language else None

    def rank(t: Dict[str, Any]) -> Tuple[int, int, int]:
        code = str(t.get("languageCode", "")).lower()
        requested = 0
        if normalized_language:
            requested = 0 if (
                code == normalized_language or
                (requested_primary is not None and code.startswith(f"{requested_primary}-")) or
                code == requested_primary
            ) else 1
        manual = 0 if t.get("kind") != "asr" else 1          # manual first
        is_en = 0 if str(t.get("languageCode", "")).startswith("en") else 1
        return (requested, manual, is_en)

    best = sorted(tracks, key=rank)[0]
    return best["baseUrl"], best.get("languageCode", "unknown")


async def _fetch_transcript_xml(client: httpx.AsyncClient, base_url: str) -> List[Dict[str, Any]]:
    res = await client.get(base_url, headers={"User-Agent": USER_AGENT}, timeout=15.0)
    res.raise_for_status()
    root = ElementTree.fromstring(res.text)
    cues = []
    for node in root.findall("text"):
        raw = "".join(node.itertext())
        text = html_lib.unescape(raw).replace("\n", " ").strip()
        if not text:
            continue
        cues.append({"start": float(node.attrib.get("start", 0)), "text": text})
    return cues


def _get_video_meta(player: Dict[str, Any]) -> Dict[str, str]:
    details = player.get("videoDetails", {})
    return {
        "title": details.get("title", "YouTube Video"),
        "author": details.get("author", ""),
        "length_seconds": details.get("lengthSeconds", ""),
        "video_id": details.get("videoId", ""),
    }


def _sectionize(cues: List[Dict[str, Any]], meta: Dict[str, str]) -> str:
    """Groups cues into SECTION_SECONDS blocks with timestamp headers.
    The '## [m:ss]' headers become section/citation anchors downstream."""
    if not cues:
        raise YouTubeExtractError(
            "This video's transcript is empty, so AtlasLM cannot ingest it."
        )
    lines: List[str] = [
        f"# {meta['title']}",
        f"Channel: {meta['author']}" if meta.get("author") else "",
        "",
    ]
    bucket_start = 0.0
    bucket_text: List[str] = []
    for cue in cues:
        if cue["start"] - bucket_start >= SECTION_SECONDS and bucket_text:
            lines.append(f"## [{_format_ts(bucket_start)}]")
            lines.append(" ".join(bucket_text))
            lines.append("")
            bucket_start = cue["start"]
            bucket_text = []
        bucket_text.append(cue["text"])
    if bucket_text:
        lines.append(f"## [{_format_ts(bucket_start)}]")
        lines.append(" ".join(bucket_text))
    return "\n".join(l for l in lines if l is not None)


async def extract_youtube_transcript(
    url: str,
    language: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Main entry point. Returns:
      { "text": <sectioned markdown transcript>,
        "title": <video title>, "video_id": ..., "language": ... }
    Raises YouTubeExtractError with a user-friendly message on failure.
    """
    video_id = extract_video_id(url)
    if not video_id:
        raise YouTubeExtractError(
            "That does not look like a valid YouTube link. Paste a video URL "
            "like https://www.youtube.com/watch?v=..."
        )
    try:
        async with httpx.AsyncClient() as client:
            watch_html = await _fetch_watch_page(client, video_id)
            player = _parse_player_response(watch_html)
            playability = player.get("playabilityStatus", {}).get("status")
            if playability not in (None, "OK"):
                raise YouTubeExtractError(
                    "AtlasLM could not access this video. It may be private, "
                    "members-only, or region-restricted."
                )
            normalized_language = normalize_transcription_language(language)
            base_url, selected_language = _pick_caption_track(player, normalized_language)
            cues = await _fetch_transcript_xml(client, base_url)
            meta = _get_video_meta(player)
            text = _sectionize(cues, meta)
            logger.info(
                "YouTube transcript extracted: %s (%s, %d cues, lang=%s)",
                video_id, meta["title"][:60], len(cues), selected_language,
            )
            return {
                "text": text,
                "title": meta["title"],
                "video_id": video_id,
                "language": selected_language,
            }
    except YouTubeExtractError:
        raise
    except httpx.HTTPError:
        raise YouTubeExtractError(
            "AtlasLM could not reach YouTube right now. Please try again."
        )
    except Exception as e:
        logger.error("YouTube extraction failed for %s: %s", video_id, e, exc_info=True)
        raise YouTubeExtractError(
            "AtlasLM could not extract a transcript from this video."
        )
