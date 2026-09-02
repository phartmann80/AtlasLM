"""ffmpeg / ffprobe helpers. Never logs file contents."""
from __future__ import annotations

import json
import logging
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, Optional

from . import MediaIngestError, MSG_NOT_MEDIA

logger = logging.getLogger("atlaslm.media.ffmpeg")


def _bin(name: str) -> str:
    found = shutil.which(name)
    if not found:
        raise MediaIngestError(
            f"This server cannot process media files because {name} is not installed."
        )
    return found


def run(args: list[str], timeout: int = 600) -> subprocess.CompletedProcess:
    started = time.monotonic()
    proc = subprocess.run(
        args,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        check=False,
    )
    duration_ms = int((time.monotonic() - started) * 1000)
    logger.info(
        "ffmpeg_cmd name=%s exit=%s duration_ms=%s",
        Path(args[0]).name,
        proc.returncode,
        duration_ms,
    )
    return proc


def probe(path: str) -> dict[str, Any]:
    ffprobe = _bin("ffprobe")
    proc = run(
        [
            ffprobe,
            "-v", "error",
            "-show_entries", "format=duration,format_name,size:stream=codec_type,codec_name,duration",
            "-of", "json",
            path,
        ],
        timeout=30,
    )
    if proc.returncode != 0:
        raise MediaIngestError(MSG_NOT_MEDIA)
    try:
        data = json.loads(proc.stdout.decode("utf-8", errors="replace") or "{}")
    except json.JSONDecodeError as exc:
        raise MediaIngestError(MSG_NOT_MEDIA) from exc
    streams = data.get("streams") or []
    fmt = data.get("format") or {}
    has_audio = any(s.get("codec_type") == "audio" for s in streams)
    has_video = any(s.get("codec_type") == "video" for s in streams)
    duration = None
    for candidate in (fmt.get("duration"), *(s.get("duration") for s in streams)):
        if candidate is None:
            continue
        try:
            duration = float(candidate)
            break
        except (TypeError, ValueError):
            continue
    if duration is None or duration <= 0 or not (has_audio or has_video):
        raise MediaIngestError(MSG_NOT_MEDIA)
    return {
        "duration": duration,
        "has_audio": has_audio,
        "has_video": has_video,
        "format_name": fmt.get("format_name") or "",
        "size": int(fmt.get("size") or 0),
        "raw": data,
    }


def convert_heic(src: str, dest: str) -> str:
    ffmpeg = _bin("ffmpeg")
    proc = run(
        [ffmpeg, "-y", "-i", src, "-frames:v", "1", dest],
        timeout=60,
    )
    if proc.returncode != 0 or not Path(dest).exists():
        raise MediaIngestError(
            "Atlas could not convert this HEIC image. Export it as PNG or JPEG and upload that file."
        )
    return dest


def to_flac_mono_16k(src: str, dest: str) -> str:
    ffmpeg = _bin("ffmpeg")
    proc = run(
        [
            ffmpeg, "-y", "-i", src,
            "-vn", "-ac", "1", "-ar", "16000", "-c:a", "flac",
            dest,
        ],
        timeout=900,
    )
    if proc.returncode != 0 or not Path(dest).exists():
        raise MediaIngestError(MSG_NOT_MEDIA)
    return dest


def strip_audio_track(src: str, dest: str) -> str:
    return to_flac_mono_16k(src, dest)


def concat_wavs(paths: list[str], dest: str, gap_ms: int = 350) -> str:
    ffmpeg = _bin("ffmpeg")
    if not paths:
        raise MediaIngestError("No audio segments were produced.")
    list_file = Path(dest).with_suffix(".concat.txt")
    lines = []
    for path in paths:
        lines.append(f"file '{path}'")
        if gap_ms and path != paths[-1]:
            # silent gap is handled by the caller inserting silence files
            pass
    list_file.write_text("\n".join(lines), encoding="utf-8")
    proc = run(
        [
            ffmpeg, "-y", "-f", "concat", "-safe", "0",
            "-i", str(list_file),
            "-c", "copy",
            dest,
        ],
        timeout=300,
    )
    list_file.unlink(missing_ok=True)
    if proc.returncode != 0 or not Path(dest).exists():
        raise MediaIngestError("Atlas could not assemble the spoken audio track.")
    return dest


def wav_to_mp3_loudnorm(src: str, dest: str) -> str:
    ffmpeg = _bin("ffmpeg")
    proc = run(
        [
            ffmpeg, "-y", "-i", src,
            "-af", "loudnorm=I=-16:TP=-1.5:LRA=11",
            "-codec:a", "libmp3lame", "-b:a", "128k",
            dest,
        ],
        timeout=300,
    )
    if proc.returncode != 0 or not Path(dest).exists():
        raise MediaIngestError("Atlas could not export the MP3 overview.")
    return dest


def still_plus_audio_mp4(image_path: str, audio_path: str, dest: str, fade_ms: int = 300) -> str:
    ffmpeg = _bin("ffmpeg")
    fade_s = max(0.05, fade_ms / 1000.0)
    proc = run(
        [
            ffmpeg, "-y",
            "-loop", "1", "-i", image_path,
            "-i", audio_path,
            "-c:v", "libx264", "-tune", "stillimage", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k",
            "-vf", f"fade=t=in:st=0:d={fade_s},fade=t=out:d={fade_s}",
            "-shortest",
            "-movflags", "+faststart",
            dest,
        ],
        timeout=600,
    )
    if proc.returncode != 0 or not Path(dest).exists():
        raise MediaIngestError("Atlas could not render a slide video.")
    return dest


def concat_mp4_crossfade(paths: list[str], dest: str, fade_ms: int = 300) -> str:
    ffmpeg = _bin("ffmpeg")
    if len(paths) == 1:
        shutil.copyfile(paths[0], dest)
        return dest
    fade_s = max(0.05, fade_ms / 1000.0)
    inputs: list[str] = []
    for path in paths:
        inputs.extend(["-i", path])
    n = len(paths)
    durations = [_probe_duration(p) for p in paths]
    video_chain = []
    audio_chain = []
    last_v = "[0:v]"
    last_a = "[0:a]"
    offset = durations[0] - fade_s
    for i in range(1, n):
        v_out = f"[v{i}]"
        a_out = f"[a{i}]"
        video_chain.append(
            f"{last_v}[{i}:v]xfade=transition=fade:duration={fade_s}:offset={max(offset, fade_s):.3f}{v_out}"
        )
        audio_chain.append(
            f"{last_a}[{i}:a]acrossfade=d={fade_s}{a_out}"
        )
        last_v, last_a = v_out, a_out
        offset = offset + durations[i] - fade_s
    filter_complex = ";".join(video_chain + audio_chain)
    proc = run(
        [
            ffmpeg, "-y", *inputs,
            "-filter_complex", filter_complex,
            "-map", last_v, "-map", last_a,
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k",
            "-movflags", "+faststart",
            dest,
        ],
        timeout=1200,
    )
    if proc.returncode != 0 or not Path(dest).exists():
        # Fallback to concat demuxer without crossfade rather than failing the job.
        logger.info("ffmpeg_crossfade_fallback count=%s", n)
        return _concat_copy(paths, dest)
    return dest


def _probe_duration(path: str) -> float:
    try:
        return float(probe(path)["duration"])
    except Exception:
        return 3.0


def _concat_copy(paths: list[str], dest: str) -> str:
    ffmpeg = _bin("ffmpeg")
    list_file = Path(dest).with_suffix(".concat.txt")
    list_file.write_text("\n".join(f"file '{p}'" for p in paths), encoding="utf-8")
    proc = run(
        [ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", str(list_file), "-c", "copy", dest],
        timeout=600,
    )
    list_file.unlink(missing_ok=True)
    if proc.returncode != 0 or not Path(dest).exists():
        raise MediaIngestError("Atlas could not assemble the video overview.")
    return dest


def write_silence_wav(dest: str, duration_s: float, sample_rate: int = 24000) -> str:
    ffmpeg = _bin("ffmpeg")
    proc = run(
        [
            ffmpeg, "-y", "-f", "lavfi",
            "-i", f"anullsrc=r={sample_rate}:cl=mono",
            "-t", f"{duration_s:.3f}",
            dest,
        ],
        timeout=30,
    )
    if proc.returncode != 0:
        raise MediaIngestError("Atlas could not generate a pause between speakers.")
    return dest


def chromium_bin() -> Optional[str]:
    from app.core.config import settings
    configured = getattr(settings, "ATLAS_CHROMIUM_BIN", "") or ""
    if configured and Path(configured).exists():
        return configured
    for name in ("chromium", "chromium-browser", "google-chrome", "chrome"):
        found = shutil.which(name)
        if found:
            return found
    return None


def html_to_png(html_path: str, dest: str, width: int, height: int) -> str:
    binary = chromium_bin()
    if not binary:
        raise MediaIngestError(
            "This server cannot render slides because a headless browser is not installed."
        )
    target = html_path
    if not target.startswith("file:") and not target.startswith("http"):
        target = Path(html_path).resolve().as_uri()
    proc = run(
        [
            binary,
            "--headless=new",
            "--disable-gpu",
            "--no-sandbox",
            "--hide-scrollbars",
            f"--window-size={width},{height}",
            f"--screenshot={dest}",
            target,
        ],
        timeout=60,
    )
    if proc.returncode != 0 or not Path(dest).exists():
        raise MediaIngestError("Atlas could not render this slide image.")
    return dest
