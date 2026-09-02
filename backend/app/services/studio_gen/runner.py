"""Studio generation: audio overview, video overview, infographic."""
from __future__ import annotations

import json
import logging
import os
import re
import tempfile
import uuid
from pathlib import Path
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models import Document, MediaJob, StudioOutput, StudioOutputCitation
from app.services.media import (
    JOB_AUDIO_OVERVIEW,
    JOB_INFOGRAPHIC,
    JOB_VIDEO_OVERVIEW,
    MediaIngestError,
    jobs as jobstore,
)
from app.services.media.ffmpeg import (
    concat_mp4_crossfade,
    concat_wavs,
    html_to_png,
    still_plus_audio_mp4,
    wav_to_mp3_loudnorm,
    write_silence_wav,
)
from app.services.media.storage import audio_root
from app.services.rag import call_model, retrieve_chunks
from app.services.tts.kokoro import get_tts_provider
from app.core.config import settings

logger = logging.getLogger("atlaslm.studio_gen")

LENGTH_MINUTES = {3: "3", 8: "8", 15: "15", "3": "3", "8": "8", "15": "15"}


def _coerce_json(raw: str) -> Any:
    text = (raw or "").strip()
    if text.startswith("```"):
        text = text.strip("`")
        newline = text.find("\n")
        if newline != -1:
            text = text[newline + 1:]
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"(\{.*\}|\[.*\])", text, re.DOTALL)
        if match:
            return json.loads(match.group(1))
        raise MediaIngestError(
            "Atlas could not assemble this Studio output from the sources. Try again."
        )


def _grounded_chunks(workspace_id: str, source_ids: list[str], k: int = 28) -> list[dict[str, Any]]:
    chunks = retrieve_chunks(
        notebook_id=str(workspace_id),
        query="key facts, numbers, claims, speakers, and main points across the sources",
        source_ids=source_ids or [],
        k=k,
    )
    if not chunks:
        raise MediaIngestError(
            "No source content is available yet. Add or finish indexing sources, then generate again."
        )
    return chunks


def _context(chunks: list[dict[str, Any]]) -> str:
    parts = []
    for idx, chunk in enumerate(chunks):
        tag = f"S{idx + 1}"
        parts.append(
            f"[{tag}] file={chunk.get('filename')} "
            f"t={chunk.get('timestamp')} page={chunk.get('page')}\n{chunk.get('text')}"
        )
    return "\n\n".join(parts)


def _cite_docs(chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen = {}
    for chunk in chunks:
        seen.setdefault(str(chunk["document_id"]), chunk)
    return [
        {
            "document_id": doc_id,
            "filename": chunk.get("filename"),
            "page_number": chunk.get("page"),
            "quote": (chunk.get("text") or "")[:280],
        }
        for doc_id, chunk in seen.items()
    ]


def process_studio_job(db: Session, job: MediaJob) -> None:
    output = db.query(StudioOutput).filter(StudioOutput.id == job.studio_output_id).first()
    if not output:
        raise MediaIngestError("This Studio job is no longer available.")
    output.status = "processing"
    output.error = None
    db.add(output)
    db.commit()
    try:
        if job.kind == JOB_AUDIO_OVERVIEW:
            _audio_overview(db, job, output)
        elif job.kind == JOB_VIDEO_OVERVIEW:
            _video_overview(db, job, output)
        elif job.kind == JOB_INFOGRAPHIC:
            _infographic(db, job, output)
        else:
            raise MediaIngestError("Unknown Studio generation type.")
    except MediaIngestError as exc:
        output.status = "failed"
        output.error = exc.public_message
        db.add(output)
        jobstore.fail(db, job, exc.public_message)
        db.commit()
        raise
    except Exception:
        output.status = "failed"
        output.error = "Atlas could not finish this Studio output. Try again."
        db.add(output)
        jobstore.fail(db, job, output.error)
        db.commit()
        raise


def _save_citations(db: Session, output: StudioOutput, citations: list[dict[str, Any]]) -> None:
    db.query(StudioOutputCitation).filter(StudioOutputCitation.studio_output_id == output.id).delete()
    for cite in citations:
        db.add(
            StudioOutputCitation(
                studio_output_id=output.id,
                document_id=uuid.UUID(str(cite["document_id"])),
                page_number=cite.get("page_number"),
                quote=cite.get("quote"),
            )
        )


def _audio_overview(db: Session, job: MediaJob, output: StudioOutput) -> None:
    payload = job.payload or {}
    minutes = int(payload.get("length_minutes") or 3)
    source_ids = payload.get("source_ids") or []
    jobstore.heartbeat(db, job, stage="script")
    chunks = _grounded_chunks(str(output.workspace_id), source_ids)
    prompt = (
        f"Write a two-host conversational audio overview about {minutes} minutes long. "
        "Host A is Maya (warm narrator). Host B is Theo (curious skeptic). "
        "Use ONLY the sources. After each factual claim add [Sn] matching the source tag. "
        "Return JSON: {\"title\": string, \"lines\": [{\"speaker\": \"A\"|\"B\", \"text\": string, \"cite\": \"S1\"}]}. "
        "ASCII punctuation only. No em dashes.\n\nSOURCES:\n" + _context(chunks)
    )
    raw = call_model(
        system="You write grounded two-host scripts. Return JSON only.",
        user=prompt,
    )
    data = _coerce_json(raw)
    lines = data.get("lines") or []
    if len(lines) < 4:
        raise MediaIngestError(
            "Atlas could not write a grounded audio overview from these sources. Add more material and try again."
        )
    jobstore.heartbeat(db, job, stage="tts")
    provider = get_tts_provider()
    voice_a = getattr(settings, "ATLAS_TTS_VOICE_A", "af_heart")
    voice_b = getattr(settings, "ATLAS_TTS_VOICE_B", "am_michael")
    work = Path(tempfile.mkdtemp(prefix="atlas-ao-"))
    wav_paths = []
    transcript = []
    cursor = 0.0
    for idx, line in enumerate(lines):
        speaker = "B" if str(line.get("speaker", "A")).upper() in {"B", "THEO"} else "A"
        text = str(line.get("text") or "").strip()
        if not text:
            continue
        voice = voice_a if speaker == "A" else voice_b
        wav_bytes = provider.synthesize(text, voice)
        path = work / f"line-{idx}.wav"
        path.write_bytes(wav_bytes)
        wav_paths.append(str(path))
        gap = work / f"gap-{idx}.wav"
        write_silence_wav(str(gap), 0.35)
        wav_paths.append(str(gap))
        transcript.append({
            "speaker": speaker,
            "name": "Maya" if speaker == "A" else "Theo",
            "text": text,
            "cite": line.get("cite"),
            "start": round(cursor, 2),
        })
        cursor += max(0.4, len(text.split()) / 2.4) + 0.35
    concat_path = str(work / "overview.wav")
    concat_wavs([p for p in wav_paths], concat_path)
    dest_dir = audio_root() / "overviews" / str(output.id)
    dest_dir.mkdir(parents=True, exist_ok=True)
    mp3_path = dest_dir / "overview.mp3"
    jobstore.heartbeat(db, job, stage="mix")
    wav_to_mp3_loudnorm(concat_path, str(mp3_path))
    citations = _cite_docs(chunks)
    output.content = {
        "title": data.get("title") or output.title,
        "length_minutes": minutes,
        "audio_path": str(mp3_path),
        "audio_url": f"/api/v1/workspaces/{output.workspace_id}/studio/{output.id}/file",
        "download_url": f"/api/v1/workspaces/{output.workspace_id}/studio/{output.id}/download",
        "transcript": transcript,
        "voices": ["Maya", "Theo"],
        "sources": citations,
        "media_type": "audio/mpeg",
    }
    output.status = "ready"
    output.error = None
    output.progress = 100
    _save_citations(db, output, citations)
    jobstore.succeed(db, job, {"path": str(mp3_path)})
    db.commit()


def _video_overview(db: Session, job: MediaJob, output: StudioOutput) -> None:
    payload = job.payload or {}
    source_ids = payload.get("source_ids") or []
    jobstore.heartbeat(db, job, stage="slides")
    chunks = _grounded_chunks(str(output.workspace_id), source_ids)
    prompt = (
        "Create a narrated slide deck, 6 to 15 slides, NotebookLM style. "
        "Use ONLY the sources. Return JSON: {\"title\": string, \"slides\": "
        "[{\"title\": string, \"bullets\": [string], \"speaker_notes\": string, "
        "\"source_refs\": [\"S1\"]}]}. ASCII punctuation only.\n\nSOURCES:\n"
        + _context(chunks)
    )
    data = _coerce_json(call_model(
        system="You write grounded slide JSON for AtlasLM. Return JSON only.",
        user=prompt,
    ))
    slides = data.get("slides") or []
    if len(slides) < 6:
        raise MediaIngestError(
            "Atlas could not build enough grounded slides from these sources. Add more material and try again."
        )
    slides = slides[:15]
    work = Path(tempfile.mkdtemp(prefix="atlas-vo-"))
    clips = []
    provider = get_tts_provider()
    voice = getattr(settings, "ATLAS_TTS_VOICE_A", "af_heart")
    rendered = []
    for idx, slide in enumerate(slides):
        jobstore.heartbeat(db, job, stage=f"slide_{idx + 1}")
        html = render_slide_html(
            title=str(slide.get("title") or f"Slide {idx + 1}"),
            bullets=[str(b) for b in (slide.get("bullets") or [])][:6],
            index=idx,
            total=len(slides),
            deck_title=str(data.get("title") or output.title),
        )
        html_path = work / f"slide-{idx}.html"
        html_path.write_text(html, encoding="utf-8")
        png_path = work / f"slide-{idx}.png"
        html_to_png(str(html_path), str(png_path), 1920, 1080)
        notes = str(slide.get("speaker_notes") or " ".join(slide.get("bullets") or [])).strip()
        wav_path = work / f"slide-{idx}.wav"
        wav_path.write_bytes(provider.synthesize(notes, voice))
        mp4_path = work / f"slide-{idx}.mp4"
        still_plus_audio_mp4(str(png_path), str(wav_path), str(mp4_path), fade_ms=300)
        clips.append(str(mp4_path))
        rendered.append({
            "title": slide.get("title"),
            "bullets": slide.get("bullets") or [],
            "speaker_notes": notes,
            "source_refs": slide.get("source_refs") or [],
            "image": f"/api/v1/workspaces/{output.workspace_id}/studio/{output.id}/slide/{idx}",
        })
    dest_dir = audio_root() / "overviews" / str(output.id)
    dest_dir.mkdir(parents=True, exist_ok=True)
    mp4_out = dest_dir / "overview.mp4"
    jobstore.heartbeat(db, job, stage="mux")
    concat_mp4_crossfade(clips, str(mp4_out), fade_ms=300)
    for idx, slide in enumerate(slides):
        src = work / f"slide-{idx}.png"
        if src.exists():
            (dest_dir / f"slide-{idx}.png").write_bytes(src.read_bytes())
    citations = _cite_docs(chunks)
    output.content = {
        "title": data.get("title") or output.title,
        "slides": rendered,
        "video_path": str(mp4_out),
        "video_url": f"/api/v1/workspaces/{output.workspace_id}/studio/{output.id}/file",
        "download_url": f"/api/v1/workspaces/{output.workspace_id}/studio/{output.id}/download",
        "sources": citations,
        "media_type": "video/mp4",
    }
    output.status = "ready"
    output.error = None
    output.progress = 100
    _save_citations(db, output, citations)
    jobstore.succeed(db, job, {"path": str(mp4_out)})
    db.commit()


def _infographic(db: Session, job: MediaJob, output: StudioOutput) -> None:
    payload = job.payload or {}
    source_ids = payload.get("source_ids") or []
    jobstore.heartbeat(db, job, stage="facts")
    chunks = _grounded_chunks(str(output.workspace_id), source_ids)
    prompt = (
        "Extract a brand-safe infographic from the sources. Return JSON: "
        "{\"headline\": string, \"kicker\": string, \"facts\": [{\"label\": string, "
        "\"value\": string, \"cite\": \"S1\"}], \"comparison\": {\"left\": string, "
        "\"right\": string, \"left_value\": string, \"right_value\": string} | null, "
        "\"timeline\": [{\"when\": string, \"what\": string}] | null, \"sources\": [\"S1\"]}. "
        "3 to 6 facts. Use only source values.\n\nSOURCES:\n" + _context(chunks)
    )
    data = _coerce_json(call_model(
        system="You extract grounded infographic JSON. Return JSON only.",
        user=prompt,
    ))
    facts = data.get("facts") or []
    if len(facts) < 3:
        raise MediaIngestError(
            "Atlas could not extract enough grounded facts for an infographic. Add more sources and try again."
        )
    from .svg_templates import render_infographic_svg
    svg = render_infographic_svg(data)
    dest_dir = audio_root() / "overviews" / str(output.id)
    dest_dir.mkdir(parents=True, exist_ok=True)
    svg_path = dest_dir / "infographic.svg"
    svg_path.write_text(svg, encoding="utf-8")
    html = (
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<style>html,body{margin:0;background:#0b1220;}</style></head>"
        f"<body>{svg}</body></html>"
    )
    html_path = dest_dir / "infographic.html"
    html_path.write_text(html, encoding="utf-8")
    png_path = dest_dir / "infographic.png"
    jobstore.heartbeat(db, job, stage="render")
    html_to_png(str(html_path), str(png_path), 1200, 1500)
    citations = _cite_docs(chunks)
    output.content = {
        "headline": data.get("headline") or output.title,
        "facts": facts,
        "comparison": data.get("comparison"),
        "timeline": data.get("timeline"),
        "svg_path": str(svg_path),
        "png_path": str(png_path),
        "image_url": f"/api/v1/workspaces/{output.workspace_id}/studio/{output.id}/file",
        "download_url": f"/api/v1/workspaces/{output.workspace_id}/studio/{output.id}/download",
        "svg_url": f"/api/v1/workspaces/{output.workspace_id}/studio/{output.id}/svg",
        "sources": citations,
        "media_type": "image/png",
    }
    output.status = "ready"
    output.error = None
    output.progress = 100
    _save_citations(db, output, citations)
    jobstore.succeed(db, job, {"path": str(png_path)})
    db.commit()


def render_slide_html(*, title: str, bullets: list[str], index: int, total: int, deck_title: str) -> str:
    items = "".join(f"<li>{_esc(b)}</li>" for b in bullets)
    return f"""<!doctype html>
<html><head><meta charset="utf-8">
<style>
  html, body {{ margin: 0; padding: 0; width: 1920px; height: 1080px; overflow: hidden; }}
  body {{
    font-family: Inter, "Liberation Sans", "DejaVu Sans", sans-serif;
    background: linear-gradient(160deg, #0b1220 0%, #151c2c 55%, #1e293b 100%);
    color: #e8eef7;
  }}
  .frame {{ box-sizing: border-box; height: 1080px; padding: 72px 96px; display: flex; flex-direction: column; }}
  .kicker {{ color: #94a3b8; letter-spacing: .18em; text-transform: uppercase; font-size: 22px; }}
  h1 {{ font-size: 64px; line-height: 1.15; margin: 28px 0 36px; color: #f8fafc; font-weight: 650; }}
  ul {{ margin: 0; padding-left: 36px; font-size: 34px; line-height: 1.45; color: #cbd5e1; }}
  li {{ margin: 14px 0; }}
  .bar {{ margin-top: auto; display: flex; justify-content: space-between; color: #7c6bb5; font-size: 20px; }}
</style></head>
<body>
  <div class="frame">
    <div class="kicker">{_esc(deck_title)}</div>
    <h1>{_esc(title)}</h1>
    <ul>{items}</ul>
    <div class="bar"><span>AtlasLM</span><span>{index + 1} / {total}</span></div>
  </div>
</body></html>
"""


def _esc(value: str) -> str:
    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
