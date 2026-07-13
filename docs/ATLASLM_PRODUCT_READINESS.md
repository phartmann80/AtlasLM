# AtlasLM product readiness

Last updated: 2026-07-11

Candidate release: `atlaslm-mastra-report-candidate-2026-07-11`

Source base commit: `d9b7eedb121e730fb1f9d4f0f535ed0cd97a0a2f`

Release state: not deployed to the public backend hostname and not approved for Vercel Production redirection.

## Candidate release scope

The approved scope for the current candidate is intentionally narrow:

```text
Notebook creation
-> real source ingestion
-> grounded cited chat
-> Report generation
-> Report persistence and reopening
```

This release is not a declaration that the full AtlasLM web platform is complete. It is the first production-gated Mastra milestone for the notebook-to-Report workflow.

## Environment tested

| Environment | Date | Result | Evidence location |
| --- | --- | --- | --- |
| Isolated backend validation stack on `212.227.44.13` | 2026-07-10 to 2026-07-11 | Passed for the notebook-to-Report vertical slice. | `docs/PRODUCTION_RELEASE_GATE_REPORT_2026-07-11.md` |
| Local/frontend candidate build | 2026-07-10 to 2026-07-11 | TypeScript, ESLint, and production build passed. | `docs/PRODUCTION_BLOCKER_STATUS_2026-07-11.md` |
| Production DNS/TLS at `api.atlaslm.cloud` | 2026-07-11 | Blocked because DNS does not resolve. | `docs/PRODUCTION_RELEASE_GATE_REPORT_2026-07-11.md` |
| Vercel Preview connected to `https://api.atlaslm.cloud` | 2026-07-11 | Not started; waits for DNS/TLS and backend HTTPS smoke. | `docs/PRODUCTION_RELEASE_GATE_REPORT_2026-07-11.md` |
| Vercel Production | 2026-07-11 | Not redirected and not authorized for cutover. | `docs/PRODUCTION_RELEASE_GATE_REPORT_2026-07-11.md` |

## Capability status for this candidate

| Capability | Status | Evidence location | Known limitations |
| --- | --- | --- | --- |
| Supabase authenticated API access | Enabled for candidate | Isolated two-user validation; `docs/PRODUCTION_RELEASE_GATE_REPORT_2026-07-11.md` | Final HTTPS auth rejection and CORS checks still required after DNS/TLS. |
| Notebook/workspace creation | Enabled for candidate | Isolated vertical-slice validation; `scripts/acceptance-matrix.js` | Public backend smoke still pending DNS/TLS. |
| Real source ingestion | Enabled for candidate | Isolated vertical-slice validation; `scripts/acceptance-matrix.js` | Full source-type matrix is not re-certified for this candidate. |
| Grounded cited chat | Enabled for candidate | Isolated vertical-slice validation; `scripts/acceptance-matrix.js` | Final citation interaction must be shown in authenticated dashboard evidence. |
| Report generation | Enabled for candidate | Mastra-backed Report validation; `migrations/010_ai_runtime_vertical_slice.sql`; `docs/PRODUCTION_RELEASE_GATE_REPORT_2026-07-11.md` | Only Report is enabled from Studio for this milestone. |
| Report persistence and reopening | Enabled for candidate | Isolated vertical-slice validation; `scripts/acceptance-matrix.js` | Must be repeated through the Vercel Preview after DNS/TLS. |
| Cross-workspace isolation | Enabled for candidate | Isolated two-user validation; `scripts/acceptance-matrix.js` | Must be repeated against deployed HTTPS candidate. |
| Layout persistence | Enabled for candidate | Isolated validation; dashboard build checks | Authenticated viewport evidence still required. |
| Study Guide | Legacy-only | Historical implementation and older smoke results only | Not approved as enabled for this candidate until revalidated with current API, persistence, auth, errors, and acceptance tests. |
| Flashcards | Disabled | Dashboard disabled-state requirements; `docs/PRODUCTION_RELEASE_GATE_REPORT_2026-07-11.md` | Must remain disabled for this release. |
| Quiz | Disabled | Dashboard disabled-state requirements; `docs/PRODUCTION_RELEASE_GATE_REPORT_2026-07-11.md` | Must remain disabled for this release. |
| Mind Map | Disabled | Dashboard disabled-state requirements; `docs/PRODUCTION_RELEASE_GATE_REPORT_2026-07-11.md` | Must remain disabled for this release. |
| Slide Deck | Disabled | Dashboard disabled-state requirements; `docs/PRODUCTION_RELEASE_GATE_REPORT_2026-07-11.md` | Must remain disabled for this release. |
| Audio Overview | Disabled | Dashboard disabled-state requirements; `docs/PRODUCTION_RELEASE_GATE_REPORT_2026-07-11.md` | Must not open an empty modal or enabled action. |
| Video Overview | Disabled | Dashboard disabled-state requirements; `docs/PRODUCTION_RELEASE_GATE_REPORT_2026-07-11.md` | Must remain disabled for this release. |
| Deep Research / Research Interest Agent | Disabled | Scope gate in `docs/PRODUCTION_RELEASE_GATE_REPORT_2026-07-11.md` | Not started for this candidate. |
| Native Android app | Disabled | Scope gate in `docs/PRODUCTION_RELEASE_GATE_REPORT_2026-07-11.md` | Android remains gated on web stability. |

## Historical evidence that is not candidate enablement

Older production smoke results from 2026-07-09 remain useful history, but they do not enable a capability in the current Mastra notebook-to-Report candidate.

In particular, older or recovered implementation evidence for Study Guide, Mind Map, Quiz, Flashcards, Audio Overview, OCR fallback, transcription language selection, or other source types must be treated as legacy-only until each capability is revalidated against the current candidate build with:

- real API behavior;
- persistence and reopening;
- authorization and cross-workspace isolation;
- error handling and disabled-state behavior;
- responsive authenticated dashboard evidence;
- acceptance tests or production smoke coverage for the current candidate.

## Open release gates

- `api.atlaslm.cloud` DNS resolution.
- TLS certificate, chain, expiry, renewal, and HTTP-to-HTTPS redirect.
- Public/private network-boundary verification.
- Candidate backend deployment without Vercel Production redirection.
- HTTPS smoke for FastAPI, database, Mastra, Redis, worker, queue, auth, CORS, ingestion, chat, citation, Report, persistence, isolation, retry, idempotency, and rollback.
- Vercel Preview connected to the verified backend.
- Authenticated dashboard evidence at desktop, laptop, tablet, and mobile widths.

## Current next step

Wait for DNS to resolve:

```text
api.atlaslm.cloud -> 212.227.44.13
```

Until that resolves publicly, do not provision production TLS, redirect Vercel Production, describe the backend as publicly available, enable unfinished Studio modules, begin Android development, or begin the Research Interest Agent.
