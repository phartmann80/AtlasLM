"""Kokoro-82M ONNX TTS running on CPU."""
from __future__ import annotations

import io
import logging
import os
import wave
from functools import lru_cache
from typing import Optional

from app.core.config import settings
from . import TTSProvider

logger = logging.getLogger("atlaslm.tts")

SAMPLE_RATE = 24000


class KokoroTTSProvider(TTSProvider):
    provider_id = "kokoro"

    def __init__(self, model_path: Optional[str] = None, voices_path: Optional[str] = None):
        self.model_path = model_path or settings.ATLAS_KOKORO_MODEL
        self.voices_path = voices_path or settings.ATLAS_KOKORO_VOICES

    def available_voices(self) -> list[str]:
        return [
            getattr(settings, "ATLAS_TTS_VOICE_A", "af_heart"),
            getattr(settings, "ATLAS_TTS_VOICE_B", "am_michael"),
        ]

    def _engine(self):
        return _load_kokoro(self.model_path, self.voices_path)

    def synthesize(self, text: str, voice: str) -> bytes:
        spoken = (text or "").strip()
        if not spoken:
            return _silence_wav(0.4)
        engine = self._engine()
        if engine is None:
            return _espeak_or_silence(spoken, voice)
        samples, rate = engine.create(spoken, voice=voice, speed=1.0, lang="en-us")
        return _float_to_wav(samples, rate)


@lru_cache(maxsize=1)
def _load_kokoro(model_path: str, voices_path: str):
    if not os.path.exists(model_path) or not os.path.exists(voices_path):
        logger.info("tts_model_missing")
        return None
    try:
        from kokoro_onnx import Kokoro
        return Kokoro(model_path, voices_path)
    except Exception:
        logger.info("tts_model_unavailable")
        return None


def _float_to_wav(samples, rate: int) -> bytes:
    import numpy as np
    pcm = np.clip(samples, -1.0, 1.0)
    ints = (pcm * 32767.0).astype("<i2")
    buf = io.BytesIO()
    with wave.open(buf, "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(int(rate or SAMPLE_RATE))
        out.writeframes(ints.tobytes())
    return buf.getvalue()


def _silence_wav(seconds: float, rate: int = SAMPLE_RATE) -> bytes:
    n = max(1, int(rate * seconds))
    buf = io.BytesIO()
    with wave.open(buf, "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(rate)
        out.writeframes(b"\x00\x00" * n)
    return buf.getvalue()


def _espeak_or_silence(text: str, voice: str) -> bytes:
    import shutil
    import subprocess
    import tempfile
    binary = shutil.which("espeak-ng")
    if not binary:
        return _silence_wav(max(0.6, len(text.split()) / 2.6))
    espeak_voice = "en+f3" if voice.lower().startswith("a") else "en+m3"
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        dest = tmp.name
    try:
        subprocess.run(
            [binary, "-v", espeak_voice, "-s", "155", "-w", dest, text],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True,
        )
        return open(dest, "rb").read()
    except Exception:
        return _silence_wav(max(0.6, len(text.split()) / 2.6))
    finally:
        try:
            os.unlink(dest)
        except OSError:
            pass


_PROVIDER: Optional[KokoroTTSProvider] = None


def get_tts_provider() -> TTSProvider:
    global _PROVIDER
    if _PROVIDER is None:
        _PROVIDER = KokoroTTSProvider()
    return _PROVIDER
