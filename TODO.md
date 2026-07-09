# AtlasLM Hardening TODO

Last updated: 2026-07-09

## Active Loop

- [x] Create a bounded hardening spec in `specs/atlaslm-hardening-loop.md`.
- [x] Add a production smoke test runner in `scripts/production-smoke.js`.
- [x] Add product readiness notes in `docs/ATLASLM_PRODUCT_READINESS.md`.
- [x] Run production smoke and record any failures.
- [x] Use failures to choose the next implementation slice.

## Verified In Production

- [x] Authenticated API requests through `www.atlaslm.cloud`.
- [x] Notebook creation.
- [x] Pasted text source ingestion.
- [x] Website source ingestion.
- [x] Image source ingestion with visual fallback.
- [x] YouTube ingestion for the two reported videos.
- [x] Source-grounded chat.
- [x] Studio study guide generation.
- [x] Audio Overview generation and playback.

## Next Engineering Queue

- [ ] Extend `scripts/production-smoke.js` coverage to Studio mind map, quiz, and flashcards.
- [ ] Fix any failing Studio output type.
- [ ] Add scanned PDF OCR fallback.
- [ ] Add transcription language selection for audio and video sources.
- [ ] Add generic media link ingestion for social video URLs where feasible.
- [ ] Replace Agent tab with real executable agent workflows.
- [ ] Evaluate and integrate a production voice service.
- [ ] Define Android API contract and build the first Android client slice.

## Needs Product Approval

- [ ] Whether short video briefs are required in v1 or can be a later tier.
- [ ] Whether to use Voicebox or another TTS/transcription stack for production voice.
- [ ] Android implementation approach if a native-only decision is required.
