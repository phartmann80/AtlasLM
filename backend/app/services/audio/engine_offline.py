# backend/app/services/audio/engine_offline.py
"""On-device TTS engine - the free, unlimited default for Audio Overview.

Uses a local, self-hosted neural voice engine so generation costs
nothing per minute and never depends on an external paid API. This keeps the
AtlasLM privacy-first promise: nothing about the user's sources leaves the box.

Wiring note: the binary + voice model paths are read from env so ops can mount
whatever voice pack they ship. If the model is missing we fall back to a silent
timed track (duration still computed from text) so the rest of the pipeline,
the transcript, export, and share, all keep working in dev.
"""
from __future__ import annotations
import os
import shutil
import struct
import subprocess
import tempfile
import wave
from typing import List

from .base import TTSEngine, ScriptLine

# Two distinct local voices, one per host slot. These are user-facing handles,
# not vendor names - swap the model files behind them freely.
VOICE_MODELS = {
    "A": os.getenv("ATLAS_VOICE_A", "/voices/atlas-host-a.onnx"),
    "B": os.getenv("ATLAS_VOICE_B", "/voices/atlas-host-b.onnx"),
}
TTS_BIN = os.getenv("ATLAS_TTS_BIN", "piper")
SAMPLE_RATE = 22050
# rough speaking rate used to estimate timing when we fall back to silence
WORDS_PER_SEC = 2.6
GAP_SEC = 0.45  # pause between turns


def _estimate_seconds(text: str) -> float:
    words = max(1, len(text.split()))
    return round(words / WORDS_PER_SEC, 2)


class OfflineTTSEngine(TTSEngine):
    voice_id = "atlas-offline"
    is_free = True

    def _have_models(self) -> bool:
        return bool(shutil.which(TTS_BIN)) and all(
            os.path.exists(p) for p in VOICE_MODELS.values()
        )

    def synthesize(self, lines: List[ScriptLine], out_path: str) -> float:
        os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
        if self._have_models():
            return self._render_real(lines, out_path)
        if shutil.which("espeak-ng"):
            return self._render_espeak(lines, out_path)
        return self._render_timed_silence(lines, out_path)

    # -- real path: render each line, concatenate with short gaps -----------
    def _render_real(self, lines: List[ScriptLine], out_path: str) -> float:
        frames = bytearray()
        cursor = 0.0
        gap_frames = b"\x00\x00" * int(SAMPLE_RATE * GAP_SEC)
        for ln in lines:
            ln.start = round(cursor, 2)
            model = VOICE_MODELS.get(ln.speaker, VOICE_MODELS["A"])
            proc = subprocess.run(
                [TTS_BIN, "--model", model, "--output_raw"],
                input=ln.text.encode("utf-8"),
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=True,
            )
            pcm = proc.stdout
            frames += pcm + gap_frames
            cursor += len(pcm) / 2 / SAMPLE_RATE + GAP_SEC
        self._write_wav(out_path, bytes(frames))
        return round(cursor, 2)

    # -- audible fallback: packaged system TTS when neural voices are absent -
    def _render_espeak(self, lines: List[ScriptLine], out_path: str) -> float:
        frames = bytearray()
        params = None
        cursor = 0.0

        with tempfile.TemporaryDirectory() as tmp:
            for idx, ln in enumerate(lines):
                ln.start = round(cursor, 2)
                voice = "en+f3" if ln.speaker == "A" else "en+m3"
                line_path = os.path.join(tmp, f"line-{idx}.wav")
                subprocess.run(
                    ["espeak-ng", "-v", voice, "-s", "155", "-w", line_path, ln.text],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=True,
                )
                with wave.open(line_path, "rb") as src:
                    if params is None:
                        params = src.getparams()
                    line_frames = src.readframes(src.getnframes())
                    rate = src.getframerate()
                    width = src.getsampwidth()
                    channels = src.getnchannels()

                frames += line_frames
                cursor += len(line_frames) / (rate * width * channels)
                gap = b"\x00" * int(rate * width * channels * GAP_SEC)
                frames += gap
                cursor += GAP_SEC

        if params is None:
            return self._render_timed_silence(lines, out_path)

        os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
        with wave.open(out_path, "wb") as out:
            out.setparams(params)
            out.writeframes(bytes(frames))
        return round(cursor, 2)

    # -- dev fallback: a correctly-timed silent track ----------------------
    def _render_timed_silence(self, lines: List[ScriptLine], out_path: str) -> float:
        cursor = 0.0
        total = 0.0
        for ln in lines:
            ln.start = round(cursor, 2)
            dur = _estimate_seconds(ln.text)
            cursor += dur + GAP_SEC
            total = cursor
        n = int(SAMPLE_RATE * total)
        self._write_wav(out_path, b"\x00\x00" * n)
        return round(total, 2)

    def _write_wav(self, out_path: str, pcm: bytes) -> None:
        with wave.open(out_path, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(SAMPLE_RATE)
            w.writeframes(pcm)
