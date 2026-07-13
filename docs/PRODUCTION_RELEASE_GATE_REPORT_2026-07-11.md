# AtlasLM production release gate report

Prepared: 2026-07-11

Status: not approved for production Vercel redirection. This is a current blocker-closure report, not a final cutover report.

Candidate release identifier: `atlaslm-mastra-report-candidate-2026-07-11`

Current repository base commit: `d9b7eedb121e730fb1f9d4f0f535ed0cd97a0a2f`

Candidate source identifier prepared on 2026-07-13: `atlaslm-mastra-report-candidate-2026-07-11-d9b7eed-7e282940fae7`

Candidate worktree patch SHA-256 prepared on 2026-07-13: `7e282940fae78f94884c9275811e15d9fb008a788224e6b43f3760778ff11ac5`

Deployed backend candidate: not deployed yet. Production backend deployment remains blocked by unresolved DNS/TLS and dashboard acceptance.

Image identifiers: not created yet for the production candidate.

Migration identifiers prepared:

- `010_ai_runtime_vertical_slice.sql`
- `010_ai_runtime.down.sql`

Known non-blocking issues:

- Existing production containers are still the current live stack and were intentionally left untouched.
- Final Vercel Preview deployment has not been configured yet because `api.atlaslm.cloud` does not resolve.
- Authenticated dashboard evidence has not been captured yet.
- Host `nginx` is not installed yet; offline syntax verification was performed with a temporary nginx container image and temporary certificate placeholders.
- DNS-pending release preparation commands and current build-input hashes are recorded in `docs/DNS_PENDING_RELEASE_PREP_2026-07-13.md`.

Secrets/private data statement:

- This report includes no secret values, token values, user credentials, private source content, or session material.

| Gate | Result | Evidence | Blocking issue |
| --- | --- | --- | --- |
| Test-user session revocation | Passed for known historical authenticated-token finding | Affected disposable test account was soft-deleted through Supabase admin API on 2026-07-11; no identity or token value recorded. | Git history still contains credential-shaped material and must stay private until coordinated cleanup. |
| Production env installed securely | Passed | `/etc/atlaslm/atlaslm.env` installed via SSH/SFTP; ownership `root:atlasdeploy`; mode `0640`; 57 variables; required values present; `atlasdeploy` can read but not write it; `atlasdeploy` group has no unrelated listed members; Compose config passes. | Final SSH hardening still deferred until cutover safety is confirmed. |
| DNS resolution | Failed | Local resolver and production server resolver cannot resolve `api.atlaslm.cloud`; current result is NXDOMAIN/no address. | Create A record `api.atlaslm.cloud -> 212.227.44.13`. |
| TLS/renewal | Blocked | TLS cannot be provisioned or verified until DNS resolves. | DNS unresolved. |
| Public/private network boundary | Partially passed for candidate, partially contained for current live stack | Candidate Compose now binds backend, frontend, Redis, and Postgres host ports to loopback only; Nginx config denies `/internal/atlas/`; offline Nginx syntax test passes. Current live backend container still exposes `0.0.0.0:8080`. On 2026-07-13, observed scanner sources were blocked and `/docs`, `/redoc`, `/openapi.json`, and `/internal/atlas/*` were rejected with temporary `DOCKER-USER` rules; see `docs/PORT_8080_CONTAINMENT_2026-07-13.md`. | Candidate deployment must replace the current public `8080` binding before final boundary can pass. |
| Backend health/readiness | Passed in isolated validation; not final production candidate | Prior isolated validation passed FastAPI health and DB readiness. Current live production was observed but left untouched. | Candidate backend not deployed behind `api.atlaslm.cloud`. |
| Migration execution | Passed in isolated validation; not final production | Additive migration executed against disposable validation DB; repeat run did not duplicate schema. | Production migration must run once during controlled deployment. |
| Vertical-slice smoke test | Passed in isolated validation; not final production | Prior isolated validation passed notebook/source/ingestion/grounded chat/Mastra Report/persistence. | Final HTTPS smoke must run after DNS, TLS, and candidate deployment. |
| Cross-workspace isolation | Passed in isolated validation; not final production | Prior two-user acceptance matrix denied cross-workspace access. | Final HTTPS smoke must repeat after candidate deployment. |
| Retry/idempotency | Partially covered | Report generation uses idempotency key in acceptance path; isolated workflow succeeded. | Dedicated retry/idempotency smoke still required against deployed candidate. |
| Rollback | Partially passed | Deploy and rollback script syntax/preflight controls validated with server Bash; non-root env config passes; release/backup paths exist. | Actual rollback test still required after versioned candidate deployment. |
| Authenticated dashboard UX | Failed/open | Frontend TypeScript, ESLint, and production build pass; unfinished Audio Overview disabled; capture procedure prepared in `docs/AUTHENTICATED_DASHBOARD_EVIDENCE_PROCEDURE.md`. | Need authenticated screenshots/evidence at required desktop, tablet, and mobile viewports after Vercel Preview is connected. |
| Vercel Preview | Blocked | Preview should point to `https://api.atlaslm.cloud` only after HTTPS backend smoke passes. | DNS/TLS unresolved. |

Scope confirmations:

- Flashcards, Quiz, Mind Map, Slide Deck, Audio Overview, and Video Overview remain disabled.
- Research Interest Agent has not been started.
- Android work has not been started.
- AtlasLM web is not described as complete.

Documentation corrections completed:

- `docs/DEPLOYMENT_RUNBOOK.md` now states `/etc/atlaslm/atlaslm.env` must be `root:atlasdeploy 0640`.
- `docs/ATLASLM_PRODUCT_READINESS.md` now uses candidate release/version, environment tested, test date, capability status, evidence location, and known limitations.
- Historical Studio smoke evidence is marked legacy-only and does not enable Flashcards, Quiz, Mind Map, Slide Deck, Audio Overview, Video Overview, or Study Guide for this candidate.
- Candidate FastAPI now disables `/docs`, `/redoc`, and `/openapi.json` when `ATLAS_ENV` is `prod` or `production`.

Prepared acceptance commands after DNS/TLS:

```bash
ATLAS_PUBLIC_BACKEND_URL=https://api.atlaslm.cloud node scripts/production-smoke-mastra.js
ATLAS_ACCEPTANCE_API_BASE=https://api.atlaslm.cloud/api/v1 REQUIRE_ATLAS_ACCEPTANCE=1 node scripts/acceptance-matrix.js
```

The acceptance tokens must be injected securely at runtime and never printed.
