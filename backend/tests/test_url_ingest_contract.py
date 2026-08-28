"""Contract tests for website/YouTube ingest language handling."""

from __future__ import annotations

import unittest

from app.services.transcription_language import normalize_transcription_language


class TranscriptionLanguageTests(unittest.TestCase):
    def test_auto_language_normalizes_to_none(self) -> None:
        self.assertIsNone(normalize_transcription_language("auto"))
        self.assertIsNone(normalize_transcription_language("detect"))
        self.assertIsNone(normalize_transcription_language(None))

    def test_language_tags_are_normalized(self) -> None:
        self.assertEqual(normalize_transcription_language("de"), "de")
        self.assertEqual(normalize_transcription_language("pt-BR"), "pt-br")

    def test_invalid_language_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            normalize_transcription_language("not a language")


if __name__ == "__main__":
    unittest.main()
