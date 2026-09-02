"""Text-to-speech provider interface."""
from __future__ import annotations

import abc


class TTSProvider(abc.ABC):
    """Pluggable TTS. Only Kokoro is shipped; a paid voice can replace it later."""

    provider_id: str = "tts"

    @abc.abstractmethod
    def synthesize(self, text: str, voice: str) -> bytes:
        """Return WAV bytes for the spoken text."""
        ...

    def available_voices(self) -> list[str]:
        return []
