# AtlasLM DNS-pending release preparation

Prepared: 2026-07-13

Status: DNS is still unresolved for `api.atlaslm.cloud`, so infrastructure mutation remains paused. Production Vercel is not redirected. Final immutable image identifiers are not created yet.

## Current DNS gate

Required DNS record:

```text
Type: A
Name/Host: api
Target/Value: 212.227.44.13
Resulting hostname: api.atlaslm.cloud
```

Current result:

```text
api.atlaslm.cloud -> NXDOMAIN / unresolved
```

## Candidate release identity

Accepted candidate release identifier:

```text
atlaslm-mastra-report-candidate-2026-07-11-d9b7eed-7e282940fae7
```

Current base commit:

```text
d9b7eedb121e730fb1f9d4f0f535ed0cd97a0a2f
```

Current branch:

```text
main
```

Current worktree state:

```text
not frozen
```

Reason: the candidate is still in a dirty worktree with pending tracked and untracked changes. Do not create immutable deployment image identifiers until the release source is committed/frozen and the final build inputs are re-hashed.

Current worktree patch SHA-256, for temporary traceability only:

```text
843e6b0f7c1e76492f5c105c1c4e91647293c5474e9dd21b1d677a2e56792b35
```

## Current build-input hashes

Recompute these after the source tree is frozen and before image creation.

| Input | SHA-256 |
| --- | --- |
| `frontend/package-lock.json` | `ff8d8b08cbe54d122b3a76e273d64832af5e07834d800ca48852316412940011` |
| `mastra/package-lock.json` | `e8c454a80ad5cb116ec7062b562304c8595ca52b76cb9a3c912642edf36b4200` |
| `backend/requirements.txt` | `9bec03c8acd3e0400dc265eeec7cf758ff63806d2965abd0ec0bd83969c54ad0` |
| `docker-compose.yaml` | `2362a5acbec1edff6439c380f338e1e62bca915e21f24f704d0a1d57e2de62bd` |
| `backend/Dockerfile` | `cd11c5e1df76f47985794658fbc44c57b3776765f33a15c41c0d33f5a4bee6cc` |
| `mastra/Dockerfile` | `77e3e978f6482c440f0937b2dc50c5c033834cd13dcfa2a26c14f5122fed2bf6` |

## Temporary public 8080 monitoring

Temporary firewall controls remain active and documented in `docs/PORT_8080_CONTAINMENT_2026-07-13.md`.

Current temporary rule markers:

```text
atlaslm-temp-8080-route-hardening
atlaslm-temp-8080-scanner-block
```

Current aggregate observation:

- route-hardening rules have matched requests for `/docs`, `/redoc`, `/openapi.json`, and `/internal/atlas/`;
- scanner-source rules have matched observed scanner traffic;
- recent backend logs did not show matching documentation/internal/scanner probes after the rules, indicating blocked traffic is not reaching FastAPI logs;
- no credentials, tokens, source content, or request bodies were recorded.

Do not grow the scanner-specific deny list as a durable security control. Final security depends on closing public `8080` after the `api.atlaslm.cloud` cutover.

## Immutable image tagging and digest capture commands

Run only after DNS resolves, the source tree is committed/frozen, and build inputs are re-hashed.

```bash
export RELEASE_ID="atlaslm-mastra-report-candidate-2026-07-11-$(git rev-parse --short HEAD)"

docker compose --env-file /etc/atlaslm/atlaslm.env -f docker-compose.yaml build backend worker mastra

docker image tag atlaslm-backend:latest "atlaslm-backend:${RELEASE_ID}"
docker image tag atlaslm-mastra:latest "atlaslm-mastra:${RELEASE_ID}"

docker image inspect "atlaslm-backend:${RELEASE_ID}" --format '{{index .RepoDigests 0}} {{.Id}}'
docker image inspect "atlaslm-mastra:${RELEASE_ID}" --format '{{index .RepoDigests 0}} {{.Id}}'
```

If Compose emits project-prefixed image names, inspect the exact built image names from:

```bash
docker compose --env-file /etc/atlaslm/atlaslm.env -f docker-compose.yaml images
```

Record immutable image ids/digests in the final release report. Do not rely only on mutable tags such as `latest`.

## Pre-deployment backup commands

Run only after DNS/TLS is ready and immediately before candidate deployment.

```bash
export RELEASE_ID="atlaslm-mastra-report-candidate-2026-07-11-$(git rev-parse --short HEAD)"
export STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
export BACKUP_DIR="/var/backups/atlaslm"

mkdir -p "$BACKUP_DIR"

docker compose --env-file /etc/atlaslm/atlaslm.env -f docker-compose.yaml exec -T db \
  pg_dump -U "${POSTGRES_USER:-atlaslm}" -d "${POSTGRES_DB:-atlaslm_db}" \
  | gzip > "$BACKUP_DIR/pre-${RELEASE_ID}-${STAMP}.sql.gz"

sha256sum "$BACKUP_DIR/pre-${RELEASE_ID}-${STAMP}.sql.gz" \
  > "$BACKUP_DIR/pre-${RELEASE_ID}-${STAMP}.sql.gz.sha256"
```

## Restore drill command

Do not run against production unless a reviewed rollback decision requires database restore.

```bash
gzip -dc /var/backups/atlaslm/<backup-file>.sql.gz \
  | docker compose --env-file /etc/atlaslm/atlaslm.env -f docker-compose.yaml exec -T db \
      psql -U "${POSTGRES_USER:-atlaslm}" -d "${POSTGRES_DB:-atlaslm_db}"
```

Normal rollback should use `scripts/rollback-backend.sh` first and should not restore database state unless a reviewed data issue exists.

## Nginx installation and TLS readiness

Run only after DNS resolves publicly and from `212.227.44.13`.

```bash
apt-get update
apt-get install -y nginx certbot python3-certbot-nginx

install -m 0644 nginx/atlaslm.cloud /etc/nginx/sites-available/atlaslm.cloud
ln -sfn /etc/nginx/sites-available/atlaslm.cloud /etc/nginx/sites-enabled/atlaslm.cloud
nginx -t

certbot --nginx -d api.atlaslm.cloud
certbot renew --dry-run
```

Verify:

```bash
curl -I http://api.atlaslm.cloud/health
curl -I https://api.atlaslm.cloud/health
openssl s_client -connect api.atlaslm.cloud:443 -servername api.atlaslm.cloud </dev/null
```

## HTTPS smoke and acceptance commands

Inject test tokens securely at runtime. Do not print them.

```bash
ATLAS_PUBLIC_BACKEND_URL=https://api.atlaslm.cloud \
  node scripts/production-smoke-mastra.js

ATLAS_ACCEPTANCE_API_BASE=https://api.atlaslm.cloud/api/v1 \
REQUIRE_ATLAS_ACCEPTANCE=1 \
ATLAS_ACCEPTANCE_TOKEN_A="$ATLAS_ACCEPTANCE_TOKEN_A" \
ATLAS_ACCEPTANCE_TOKEN_B="$ATLAS_ACCEPTANCE_TOKEN_B" \
  node scripts/acceptance-matrix.js
```

Expected acceptance coverage:

- authentication rejection for missing/invalid tokens;
- CORS restricted to approved AtlasLM origins;
- source ingestion;
- grounded cited chat;
- Report generation;
- Report persistence and reopening;
- cross-workspace isolation;
- retry/idempotency;
- rollback.

## Vercel Preview variables

Prepare but do not activate until the backend HTTPS smoke passes.

```text
NEXT_PUBLIC_API_BASE=https://api.atlaslm.cloud/api/v1
NEXT_PUBLIC_API_URL=https://api.atlaslm.cloud
ATLAS_BACKEND_URL=https://api.atlaslm.cloud
```

Production Vercel remains unchanged until final cutover approval.

## Synthetic dashboard evidence data

Use only synthetic content:

```text
AtlasLM release evidence source. The approved workflow is notebook creation, source ingestion, grounded cited chat, Report generation, and Report reopening after refresh.
```

Do not use private, customer, personal, or production source content in dashboard evidence.

Authenticated evidence procedure:

```text
docs/AUTHENTICATED_DASHBOARD_EVIDENCE_PROCEDURE.md
```

