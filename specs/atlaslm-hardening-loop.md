# AtlasLM Hardening Loop

## Objective

Turn AtlasLM from a patched dashboard into a real production web app with an Android-ready backend. Work in bounded loops: choose the highest-priority product slice, implement it, test it, update notes, and report what passed, failed, and comes next.

## Current Product Goal

AtlasLM must behave like a source-grounded research assistant over user-provided materials:

- Users can add documents, pasted text, websites, YouTube videos, audio, and images.
- Atlas AI answers from ready notebook sources with citations.
- Studio can generate study guides, mind maps, quizzes, and flashcards from indexed sources.
- Audio Overview creates a playable spoken overview from ready sources.
- The app is honest about partial features and must not show inert mock controls as if they are finished.
- The backend API must be stable enough for a native Android client to use.

## Phases

1. Production truth and regression harness
   - Add a repeatable production smoke test that exercises auth, notebook creation, text notes, website ingest, image ingest, YouTube ingest, grounded chat, Studio, and Audio Overview.
   - Update project notes with what is real, partial, mocked, and next.

2. Core source ingestion hardening
   - Make all source types reliable, observable, and language-aware where applicable.
   - Finish generic media link ingestion beyond YouTube where legally and technically possible.

3. Agent and Studio completion
   - Replace static Agent cards with real agent tasks.
   - Make all Studio outputs pass production smoke tests.
   - Add useful empty states and failure recovery.

4. Voice and media generation
   - Integrate a proper voice service, likely a Voicebox-style service or equivalent server-side TTS.
   - Make Audio Overview quality acceptable for users.
   - Decide whether short video briefs are in v1 or held for a later paid tier.

5. Android-ready API and native app
   - Stabilize mobile auth/session API expectations.
   - Create an Android client that can sign in, list notebooks, add sources, chat, and play audio.

## Definition Of Done For Current Slice: Scanned PDF OCR

This slice is complete when:

- PDF ingestion extracts normal embedded text as before.
- PDF ingestion OCRs image-only/scanned pages when no embedded text is present.
- Empty or unreadable PDFs still fail honestly with a useful error.
- The production smoke command uploads an image-only PDF and verifies that it becomes a ready source.
- Project notes record scanned PDF OCR as verified, or record the exact failure if it does not pass.

## Verification Commands

- `python -m compileall backend/app` if backend code changes
- `node --check scripts/production-smoke.js`
- `node scripts/production-smoke.js`

## Iteration Budget

Two build-review iterations for this slice before reporting a blocker.

## Approval Gates

Ask before:

- Changing pricing or product tier promises.
- Adding paid third-party services.
- Performing destructive database or server operations.
- Making Android technology choices that lock the app into a framework.
- Deploying broad architectural changes without a rollback path.
