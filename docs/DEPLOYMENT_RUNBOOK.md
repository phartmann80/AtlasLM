# AtlasLM controlled deployment runbook

## Approved topology

```text
https://atlaslm.vercel.app
        -> https://api.atlaslm.cloud
        -> Nginx/TLS on 212.227.44.13
        -> FastAPI on 127.0.0.1:8080
        -> private Mastra on the Compose network
        -> private worker, Redis, and Supabase/PostgreSQL
```

The raw IP is never placed in the production frontend API URL. Mastra, Redis, worker, database, and `/internal/atlas/*` routes are not public Nginx locations.

## Server prerequisites

- Ubuntu/Debian-compatible OS with current security updates.
- Non-root deployment user with Docker and narrowly scoped sudo access.
- Docker Engine and Compose plugin.
- Firewall exposing only SSH from the approved administration network and HTTPS ports 80/443.
- DNS A/AAAA record `api.atlaslm.cloud -> 212.227.44.13`.
- Certbot certificate for `api.atlaslm.cloud`.
- `/etc/atlaslm/atlaslm.env` owned by `root`, group `atlasdeploy`, mode `0640`. This lets the non-root `atlasdeploy` account read the Compose environment file for routine deployments while preventing it from modifying values.
- No unrelated user should belong to the `atlasdeploy` group.
- `/opt/atlaslm/releases`, `/opt/atlaslm/current`, and `/var/backups/atlaslm` with documented retention.

## Candidate network boundary

The public production boundary is Nginx on ports 80/443 only.

The candidate Compose file must keep host service ports loopback-only:

- FastAPI backend: `127.0.0.1:8080:8000`
- optional containerized frontend: `127.0.0.1:3010:3000`
- PostgreSQL: `127.0.0.1:5435:5432`
- Redis: `127.0.0.1:6385:6379`

Mastra, worker, Redis, Postgres, and internal Atlas tool endpoints must not be public. The `api.atlaslm.cloud` Nginx server block must deny `/internal/atlas/` and proxy only the public backend surface.

## Runtime hardening baseline

Before deployment, confirm required services have:

- `restart: unless-stopped` or a reviewed equivalent restart policy;
- health checks for database, Redis, backend, worker queue dependency, Mastra, and any containerized frontend path used by the deployment;
- resource limits;
- JSON log rotation;
- no secret values in Compose, deployment logs, screenshots, or shell history.

## Deployment

1. Audit OS, CPU, RAM, disk, Docker, firewall, DNS, and TLS.
2. Confirm a backup target and take a pre-deployment PostgreSQL dump.
3. Run the secret scan and migration safety check locally and in CI.
4. Transfer or check out the versioned release as the deployment user.
5. Run `scripts/deploy-backend.sh` with `ENV_FILE=/etc/atlaslm/atlaslm.env`.
6. Verify FastAPI `/health`, the private Mastra `/health`, worker/Redis readiness, and Nginx/TLS.
7. Run `scripts/production-smoke-mastra.js` and the authenticated acceptance suite.
8. Deploy the Vercel preview with `NEXT_PUBLIC_API_BASE=https://api.atlaslm.cloud/api/v1`.
9. Run the full notebook-to-report acceptance sequence before production promotion.

## Rollback

1. Set all runtime flags back to the last known-good values if Mastra is implicated.
2. Identify the last healthy release under `/opt/atlaslm/releases`.
3. Run `scripts/rollback-backend.sh <known-good-release-id>`.
4. Re-run public health, smoke, and authenticated isolation checks.
5. Restore the pre-deployment database backup only if a reviewed data issue exists. The normal rollback does not delete or rewrite recovered AtlasLM data.

Retain at least the current release, the immediately prior known-good release, and the pre-deployment backup until the release is accepted and monitoring is clean.

## Maintenance and monitoring

Monitor CPU, memory, disk, queue depth, request latency, 4xx/5xx rates, worker failures, and Mastra/provider errors. Rotate structured logs. Retain database and configuration backups. Do not log tokens, raw private excerpts, or signed internal context.
