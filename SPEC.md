# AtlasLM Mastra notebook-to-report milestone

Status: Build in progress
Owner: Codex working with Paul Hartmann
Deployment target: Vercel frontend + backend services on `212.227.44.13`

## Product flow

Create notebook -> add a real source -> ingest and index -> confirm ready status -> ask a grounded question -> verify citations -> generate a Report -> persist and reopen the Report.

The first agent is `NotebookResearchAgent`. Research Interest Agent and unfinished Studio modules are out of scope for this milestone.

## Delivery stages

### Research

- Confirm the existing FastAPI, Supabase/Postgres/pgvector, Redis, ingestion worker, frontend, and Nginx boundaries.
- Confirm Mastra is a private TypeScript service, not a browser dependency.
- Confirm the Vercel frontend uses a dedicated HTTPS API hostname, never the backend IP.

### Build

- Add additive `ai_runs`, `ai_run_events`, conversation metadata, report metadata, and workspace layout migrations.
- Add signed FastAPI-to-Mastra context with FastAPI reauthorization at every tool boundary.
- Add the seven typed Atlas tools.
- Add the private Mastra service with NotebookResearchAgent and Report workflow.
- Repair the dashboard shell, docked resizing, collapse/restore, mobile overflow, and empty states.

### Review

- Inspect every new public and internal route for workspace/source authorization.
- Verify no model-controlled identity fields are trusted.
- Verify no raw private source content enters observational memory or unredacted traces.
- Check the diff for simulated timers, sample sources, hardcoded answers, empty output modals, and accidental secret exposure.

### Test

Deterministic gates must pass before sign-off:

- Python compile and backend tests.
- Mastra TypeScript build.
- Frontend TypeScript check and ESLint for changed files.
- Migration syntax and idempotency review.
- Cross-workspace authorization tests.
- Citation verification tests.
- Report persistence, reopen, failure, retry, and idempotency tests.
- Dashboard viewport and keyboard-resize checks.

### Integrate

- Apply migrations with a reviewed rollback path.
- Deploy backend services and private Mastra service to the approved server.
- Deploy frontend to Vercel with the HTTPS backend hostname.
- Run production smoke and isolation acceptance.
- Record deployment commit, request/trace IDs, and test results without secrets or private source content.

## Acceptance gates

The milestone is not complete until a fresh notebook demonstrates:

1. A real uploaded source reaches ready status after actual ingestion.
2. Grounded chat returns source citations that resolve to the correct indexed chunks.
3. Unsupported evidence produces a clear missing-evidence response.
4. A Report is generated from the same authorized source scope.
5. The Report contains verified citations, persists, and reopens after refresh.
6. Failed Report runs provide a useful reason and safe retry.
7. Dashboard resizing works with mouse and keyboard, collapse/restore works, and Reset layout restores defaults.
8. Two workspaces cannot access each other's sources, runs, outputs, or layouts.
9. Mastra can be rolled back independently with `ATLAS_CHAT_RUNTIME`, `ATLAS_REPORT_RUNTIME`, and `ATLAS_RESEARCH_RUNTIME`.

## Deployment prerequisites

Production deployment is blocked until secure server access is provided outside chat:

- non-root SSH username and authorized public key
- required sudo scope
- approved backend hostname, proposed as `api.atlaslm.cloud`
- DNS A/AAAA record and TLS certificate path
- firewall ports, limited to HTTPS and controlled SSH
- deployment directory and Docker/runtime availability

No private keys, passwords, tokens, or environment values belong in this repository or chat.
