# AtlasLM production blocker status

Prepared: 2026-07-11

Status: production remains unredirected. The isolated notebook-to-report milestone is technically proven, but production cutover is still blocked.

## Milestone accepted as proven in isolation

The approved isolated workflow has passed prior validation:

`Notebook -> real source -> ingestion -> grounded cited answer -> Mastra Report -> persistence and reopening`

Covered evidence:

- Backend image build on `212.227.44.13`
- FastAPI health and database readiness
- Private FastAPI-to-Mastra connectivity
- Redis connectivity and worker restart
- Additive migration execution against a disposable database
- Two-user vertical-slice test
- Real source ingestion
- Grounded chat with citations
- Mastra-backed Report generation
- Report persistence and reopening
- Cross-workspace isolation
- Layout persistence
- Frontend TypeScript, ESLint, and production build
- Deployment and rollback script syntax/preflight controls
- CRLF shell execution fix
- Blank `RESEARCH_HTTP_TIMEOUT` fix
- Credential-shaped test fixture cleanup
- Next.js route typing fix
- Unfinished Audio Overview behavior disabled

## Blocker 1: credential and Git-history remediation

Status: session revocation complete; Git-history cleanup remains required before public or broad sharing.

Completed:

- Current-tree scan passes: `scripts/secret-scan.ps1`
- History scan reviewed in redacted form: `scripts/secret-scan.ps1 -History`
- Redacted disposition added: `docs/SECURITY_HISTORY_DISPOSITION.md`
- Current code no longer embeds the historical authenticated test token fixture.
- Current code no longer embeds the historical frontend verification anon key fixture.
- Owner classification decision accepted on 2026-07-11.
- Supabase anon/public browser key rotation is not required solely from the reported findings.
- The historical authenticated-token finding was traced to one disposable test account.
- Token-level global sign-out was attempted and rejected by Supabase because the historical access token is expired.
- The affected disposable test account was soft-deleted through the Supabase admin API on 2026-07-11.

Still required:

- Review of Vercel Production, Preview, and Development variables after any rotation.
- Secure update of backend server environment after any rotation.
- Coordinated Git-history rewrite if the repository is shared, may become public, or contains actual secret material.
- Re-scan of rewritten history if rewrite is approved.

## Blocker 2: DNS and TLS

Status: blocked by DNS.

Current evidence:

- `api.atlaslm.cloud` does not resolve from the local resolver.
- `api.atlaslm.cloud` does not resolve from the production server resolver.
- `https://api.atlaslm.cloud/health` fails before TLS because the hostname is unresolved.
- `node scripts/production-smoke-mastra.js` fails with `getaddrinfo ENOTFOUND api.atlaslm.cloud`.

Required owner action:

- Create DNS record:
  - Type: `A`
  - Name: `api`
  - Target: `212.227.44.13`
  - Hostname: `api.atlaslm.cloud`

Still required after DNS resolves:

- Provision TLS.
- Verify valid certificate chain and renewal.
- Verify HTTPS redirect behavior.
- Verify no certificate-name mismatch.
- Verify public exposure is limited to the intended backend endpoint.
- Verify authenticated routes reject missing and invalid tokens.
- Verify CORS allows only approved AtlasLM production and controlled preview origins.

## Blocker 3: non-root production deployment setup

Status: production env installed; final SSH hardening remains intentionally deferred until cutover safety is confirmed.

Completed on `212.227.44.13`:

- Server is Ubuntu `24.04.4 LTS`.
- Non-root deploy account exists: `atlasdeploy`.
- `atlasdeploy` password is locked.
- `atlasdeploy` is in the `docker` group.
- Approved public key is installed in `/home/atlasdeploy/.ssh/authorized_keys`.
- SSH directory permissions:
  - `/home/atlasdeploy/.ssh`: `atlasdeploy:atlasdeploy 700`
  - `/home/atlasdeploy/.ssh/authorized_keys`: `atlasdeploy:atlasdeploy 600`
- Deployment paths:
  - `/opt/atlaslm`: `root:atlasdeploy 2775`
  - `/opt/atlaslm/releases`: `atlasdeploy:atlasdeploy 2775`
  - `/var/backups/atlaslm`: `atlasdeploy:atlasdeploy 2775`
  - `/etc/atlaslm`: `root:atlasdeploy 750`
- Direct SSH as `atlasdeploy` works with the approved key.
- `atlasdeploy` can run `docker ps`.
- `atlasdeploy` can write releases/backups.
- `atlasdeploy` cannot write `/etc/atlaslm`.
- No isolated validation containers remain running.
- `/etc/atlaslm/atlaslm.env` installed on 2026-07-11 through SSH/SFTP without printing values.
- `/etc/atlaslm/atlaslm.env` ownership and mode: `root:atlasdeploy 0640`.
- `atlasdeploy` can read `/etc/atlaslm/atlaslm.env` for deployment and cannot write it.
- The env file contains 57 names, with required deployment values present.
- `docker compose --env-file /etc/atlaslm/atlaslm.env -f docker-compose.yaml config -q` passes on the server checkout.

Still required:

- Add narrowly scoped sudo permissions only if an operation requires them.
- Disable password-based SSH after final key access confirmation.
- Disable direct root SSH where operationally safe after deploy access and rollback procedures are confirmed.
- Confirm release retention, health checks, restart policies, resource limits, structured log rotation, and backup/restore instructions against the final production layout.

Current live production containers were observed and left untouched:

- `atlaslm-backend-1`
- `atlaslm-worker-1`
- `atlaslm-redis-1`
- `atlaslm-db-1`

Current live boundary note:

- The current live backend container exposes `0.0.0.0:8080`.
- The candidate Compose file has been corrected to bind FastAPI to `127.0.0.1:8080:8000`; final boundary verification must confirm the public `8080` exposure is gone after candidate deployment.
- On 2026-07-13, direct external checks confirmed `8080` is reachable. Before route hardening, `/health` returned `200`, `/docs` and `/openapi.json` were public, and `/internal/atlas/tools/getNotebookContext` returned `401`.
- On 2026-07-13, direct external checks confirmed Redis `6385`, PostgreSQL `5435`, Mastra `8110`, worker/internal `8000`, and frontend container `3010` are not reachable publicly.
- Because `https://www.atlaslm.cloud/api/v1/health` is active while `api.atlaslm.cloud` remains NXDOMAIN, the current Vercel proxy is treated as likely dependent on the raw `8080` backend endpoint until the candidate release replaces it.
- Temporary `DOCKER-USER` rules now block observed scanner sources marked with `atlaslm-temp-8080-scanner-block`; see `docs/PORT_8080_CONTAINMENT_2026-07-13.md`.
- Temporary `DOCKER-USER` rules now reject public `/docs`, `/redoc`, `/openapi.json`, and `/internal/atlas/*` requests on `8080` before they reach FastAPI, while `/health`, direct `/api/v1/*`, and the Vercel `/api/v1/*` proxy still respond.

Candidate hardening completed locally:

- Backend, frontend, Redis, and Postgres host ports are loopback-only in `docker-compose.yaml`.
- Required Compose services have restart policies.
- Candidate Compose adds health checks for Redis, backend, worker queue dependency, Mastra, and the optional containerized frontend path.
- Candidate Compose adds resource limits and JSON log rotation.
- Candidate Compose config validates successfully on the server with dummy values.
- Nginx config denies `/internal/atlas/` on the public API hostname.
- Nginx config passes offline syntax validation with a temporary nginx container and temporary certificate placeholders.
- Candidate FastAPI disables `/docs`, `/redoc`, and `/openapi.json` when `ATLAS_ENV` is `prod` or `production`.

## Blocker 4: authenticated dashboard UX sign-off

Status: not closed.

Completed:

- Frontend candidate builds successfully.
- TypeScript validation passes.
- ESLint validation passes for the dashboard candidate.
- Unfinished Audio Overview action is disabled rather than opening an empty modal.

Still required:

- Capture authenticated evidence from the deployed candidate build at:
  - `1440 x 900`
  - `1366 x 768`
  - `1024 x 768`
  - `768 x 1024`
  - representative narrow mobile viewport
- Evidence must show layout, resizing, keyboard resizing, collapse/restore, persistence after refresh, Reset layout, tablet/mobile navigation, guided empty states, real source states, grounded chat citation interaction, generated Report content reopened, and disabled unfinished modules with explanations.
- Authentication capture must use a safe test-session mechanism or manual capture without logging credentials or session tokens.

Current note:

- Local authentication automation needs a Supabase SSR cookie/session path. LocalStorage alone is insufficient because the dashboard middleware reads the authenticated user from SSR cookies.
- Production DNS/TLS is still blocked, so Vercel must not be redirected to `api.atlaslm.cloud`.

## Production cutover decision

Do not redirect Vercel Production and do not describe AtlasLM web as complete.

The next allowed production sequence starts only after:

1. Git-history remediation is approved or explicitly deferred with owner signoff for private-only release.
2. `/etc/atlaslm/atlaslm.env` exists with restricted permissions.
3. `api.atlaslm.cloud` resolves to `212.227.44.13`.
4. TLS and HTTPS smoke tests pass.
5. Authenticated dashboard evidence is captured and accepted.

Unfinished Studio modules remain disabled: Flashcards, Quiz, Mind Map, Slide Deck, Audio Overview, and Video Overview.
