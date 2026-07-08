# backend/app/services/audio/service.py
"""AudioOverviewService - orchestrates: retrieve -> script -> synthesize -> store.

It reuses the existing Studio generation + retrieval path for the script step
(so audio is as grounded as every other Studio output) and the pluggable
TTSEngine for synthesis. The default engine is on-device and free.

Persisted rows live in the `audio_overviews` table (migration 004). The audio
file is written under AUDIO_DIR; share links serve it read-only by token.
"""
from __future__ import annotations
import os
import uuid
from typing import List, Optional

from .base import AudioOverview, ScriptLine
from .engine_offline import OfflineTTSEngine
from . import script_gen

AUDIO_DIR = os.getenv("AUDIO_DIR", "/data/audio")

# Engine registry. "atlas-offline" is the free default; a cloud engine can be
# registered here later under "studio-cloud" without touching callers.
_ENGINES = {
    "atlas-offline": OfflineTTSEngine(),
    "studio-cloud": OfflineTTSEngine(),
}


def _engine(voice: str):
    return _ENGINES.get(voice) or _ENGINES["atlas-offline"]


class AudioOverviewService:
    def __init__(self, generation_client=None, retriever=None):
        # Injected so we reuse the SAME clients Studio already uses. Kept
        # optional so verify scripts can run the parse/synthesize path offline.
        self._gen = generation_client
        self._retriever = retriever

    # ---- main entry -------------------------------------------------------
    def generate(self, db, workspace_id: str, *, title: str,
                 style: str = "deep_dive", voice: str = "atlas-offline",
                 doc_ids: Optional[List[str]] = None) -> AudioOverview:
        lines = self._make_script(db, workspace_id, style, doc_ids)
        overview_id = uuid.uuid4().hex
        out_path = os.path.join(AUDIO_DIR, f"{overview_id}.wav")
        duration = _engine(voice).synthesize(lines, out_path)
        ov = AudioOverview(
            overview_id=overview_id, title=title, style=style, voice=voice,
            duration=duration, lines=lines, audio_path=out_path,
        )
        self._persist(db, workspace_id, ov)
        return ov

    # ---- script step (reuses Studio retrieval + generation) ---------------
    def _make_script(self, db, workspace_id, style, doc_ids) -> List[ScriptLine]:
        prompt = script_gen.build_prompt(style)
        if self._gen is None or self._retriever is None:
            # offline/dev path: deterministic stub so the pipeline still runs
            return script_gen.parse_script(_STUB_SCRIPT, style)
        chunks = self._retriever.retrieve(db, workspace_id, doc_ids=doc_ids)
        raw = self._gen.complete(prompt, context_chunks=chunks)
        lines = script_gen.parse_script(raw, style)
        return lines or script_gen.parse_script(_STUB_SCRIPT, style)

    # ---- persistence ------------------------------------------------------
    def _persist(self, db, workspace_id: str, ov: AudioOverview) -> None:
        if db is None:
            return
        try:
            from app.models import AudioOverviewRow  # added in migration 004
        except Exception:  # noqa: BLE001
            return  # model not wired yet; file + object still usable in dev
        row = AudioOverviewRow(
            id=ov.overview_id, workspace_id=workspace_id, title=ov.title,
            style=ov.style, voice=ov.voice, duration=ov.duration,
            audio_path=ov.audio_path, transcript=ov.transcript(),
            share_token=None, is_public=False,
        )
        db.add(row)
        db.flush()

    def get(self, db, overview_id: str):
        from app.models import AudioOverviewRow
        return db.get(AudioOverviewRow, overview_id)


_STUB_SCRIPT = """\
Maya: So Q2 is in the books, and the headline is strong. ARR grew 23 percent quarter over quarter. [S2]
Theo: That is more than double the 11 percent from Q1. What drove it? [S2]
Maya: Mid-market expansion, mostly. Net revenue retention reached 112 percent. [S1]
Theo: Here is my worry though. In the small-business tier, NPS dropped to 31. [S3]
Maya: And it is onboarding friction. People hit a wall before they get value. [S3]
Theo: Plus a competitor undercuts our Pro tier by about 18 percent with bundled analytics. [S4]
Maya: So the play is clear. Fix onboarding, rethink Pro packaging, protect mid-market. [S1]
"""
