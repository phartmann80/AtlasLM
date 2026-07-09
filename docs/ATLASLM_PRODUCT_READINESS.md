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
- 2026-07-09: Studio smoke coverage was expanded and passed for study guide, mind map, quiz, and flashcards.
- 2026-07-09: Scanned PDF OCR fallback was added, deployed, and verified with an image-only PDF upload in production smoke.
- 2026-07-09: Transcription language selection was added for YouTube and audio uploads. YouTube `language: "en"` ingestion passed production smoke; audio language pass-through was verified in the deployed backend container.

## Real And Verified

These paths have production smoke coverage:

- Supabase authenticated API calls.
- Notebook/workspace creation.
- Pasted text and notebook notes as ready sources.
- Website ingestion for visible page text.
- Image ingestion through OCR, with visual AI fallback when OCR finds no text.
- Scanned/image-only PDF ingestion through OCR fallback.
- YouTube ingestion for the two reported test videos, including explicit language selection.
- Source-grounded chat over ready sources.
- Studio study guide, mind map, quiz, and flashcard generation.
- Audio Overview generation and playback through an authenticated WAV stream.

Run:

```bash
node scripts/production-smoke.js
```

## Partial

- Audio voice quality is functional but not final. The backend now produces audible speech through a packaged fallback when neural voice models are missing. A higher-quality Voicebox-style service is still needed.
- YouTube works through captions first and media transcription fallback. Some private, members-only, region-restricted, or blocked videos can still fail because YouTube refuses access.
- Audio file uploads pass a selected transcription language through the API, queue, worker, and Whisper loader. Production smoke does not yet upload a spoken audio fixture by default.
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

## Loop Phases

1. Production truth and regression harness
   - Status: complete for current critical paths.
   - Smoke runner added.
   - Product readiness notes added.

2. Core source ingestion hardening
   - Add generic media-link ingestion where feasible.
   - Improve error messaging for blocked media.
   - Continue expanding source-type smoke coverage.

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

Add generic media-link ingestion for public social/video/audio URLs where feasible.

Reason: users expect to paste YouTube, Instagram, TikTok, LinkedIn, and other media links into one source flow. YouTube is real; the broader media-link path is still the biggest visible ingestion gap.

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
