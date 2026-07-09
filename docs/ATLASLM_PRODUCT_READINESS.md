# AtlasLM Product Readiness

Last updated: 2026-07-09

## Goal

AtlasLM must become a real source-grounded research app, then an Android app that uses the same backend API. The web app is the reference client. The backend must be reliable enough that Android can reuse auth, notebooks, source ingestion, chat, Studio outputs, and audio playback without special-case hacks.

## Current Production Reality

Production frontend:

- `https://www.atlaslm.cloud`

Production backend:

- Server-hosted FastAPI backend behind the Vercel API proxy.

Latest production smoke:

- 2026-07-09: `node scripts/production-smoke.js` passed all checks against `https://www.atlaslm.cloud`.

## Real And Verified

These paths have production smoke coverage:

- Supabase authenticated API calls.
- Notebook/workspace creation.
- Pasted text and notebook notes as ready sources.
- Website ingestion for visible page text.
- Image ingestion through OCR, with visual AI fallback when OCR finds no text.
- YouTube ingestion for the two reported test videos.
- Source-grounded chat over ready sources.
- Studio study guide generation.
- Audio Overview generation and playback through an authenticated WAV stream.

Run:

```bash
node scripts/production-smoke.js
```

## Partial

- Audio voice quality is functional but not final. The backend now produces audible speech through a packaged fallback when neural voice models are missing. A higher-quality Voicebox-style service is still needed.
- YouTube works through captions first and media transcription fallback. Some private, members-only, region-restricted, or blocked videos can still fail because YouTube refuses access.
- Image ingestion can index OCR text or a visual description. It is not a full vision Q&A system yet.
- Deep Research/source discovery exists, but it still needs a dedicated production smoke test and better empty/error states.
- Agent tab launches real app areas, but it is not yet a full autonomous agent with task planning and deliverable execution.

## Not Yet Real

- Generic Instagram, TikTok, LinkedIn, and arbitrary social video transcription.
- Premium Studio HD voice.
- Short vertical video brief generation.
- Native Android app.
- Invite email delivery.
- Google/GitHub signup buttons.
- Scanned PDF OCR fallback.

## Loop Phases

1. Production truth and regression harness
   - Status: complete for current critical paths.
   - Smoke runner added.
   - Product readiness notes added.

2. Core source ingestion hardening
   - Add language choice for transcription.
   - Add generic media-link ingestion where feasible.
   - Improve error messaging for blocked media.
   - Add scanned PDF OCR.

3. Agent and Studio completion
   - Make Agent tab execute real workflows.
   - Add smoke tests for all Studio output types.
   - Add recovery actions when generation fails.

4. Voice and media generation
   - Evaluate Voicebox service integration.
   - Add production TTS service with stable voice selection.
   - Decide short-video scope for v1.

5. Android app
   - Freeze mobile API contract.
   - Build native Android sign-in, notebook list, source upload, chat, Studio output, and audio playback.

## Next Highest-Priority Task

Add production smoke coverage for all remaining Studio outputs and then fix any failing output type:

- Mind map
- Quiz
- Flashcards

Reason: Studio is a core user promise, it feeds Android later, and it is already part of the visible dashboard.

## Operating Loop

For each loop:

1. Understand the goal.
2. Break into phases.
3. Choose the next highest-priority slice.
4. Implement it.
5. Test it locally and, when relevant, in production.
6. Fix failures inside the iteration budget.
7. Update this document.
8. Report completed, failed, and next.
