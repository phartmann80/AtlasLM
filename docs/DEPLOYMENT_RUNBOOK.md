# AtlasLM self-hosted deployment runbook

## Production topology

```text
https://www.atlaslm.cloud
        -> Nginx/TLS on 212.227.44.13
        -> Next.js on 127.0.0.1:3010
        -> https://api.atlaslm.cloud
        -> Nginx/TLS on 212.227.44.13
        -> FastAPI on a loopback-only candidate port
        -> private Mastra, worker, Redis, and PostgreSQL networks
```

Vercel is not part of the production request path. The raw server IP is not placed in browser-visible configuration. Mastra, Redis, the worker, PostgreSQL, and `/internal/atlas/*` are not public Nginx locations.

## Server baseline

- Ubuntu with current security updates.
- Non-root `atlasdeploy` user with Docker access and narrowly scoped sudo rights.
- Docker Engine and Compose plugin.
- Nginx and Certbot.
- Firewall/provider boundary exposing only required SSH administration and ports 80/443.
- DNS A records:
  - `atlaslm.cloud -> 212.227.44.13`
  - `www.atlaslm.cloud -> 212.227.44.13`
  - `api.atlaslm.cloud -> 212.227.44.13`
- Certificates:
  - `atlaslm.cloud` certificate covers both `atlaslm.cloud` and `www.atlaslm.cloud`.
  - `api.atlaslm.cloud` has its own certificate.
- `/etc/atlaslm/atlaslm.env` is `root:atlasdeploy` mode `0640`.
- `/opt/atlaslm/frontend-releases` and `/opt/atlaslm/releases` are group-writable only by `atlasdeploy`.
- Database backups remain under `/var/backups/atlaslm` with reviewed retention.

## Public and private boundaries

Only Nginx listens publicly on 80/443. Application ports remain loopback-only:

- Next.js frontend: `127.0.0.1:3010:3000`
- candidate FastAPI: loopback-only release port such as `127.0.0.1:18082:8000`
- legacy FastAPI port `8080` must be removed from public exposure after cutover
- PostgreSQL and Redis are either Docker-network-only or loopback-only

Mastra and workers have no host port. Both public Nginx hosts deny `/internal/atlas/`. The API host also denies `/docs`, `/redoc`, and `/openapi.json` in production.

## Immutable frontend release

1. Validate TypeScript, ESLint, Next.js production build, Docker Compose rendering, and Nginx syntax locally.
2. Create an owner-attributed Git commit and immutable release identifier.
3. Transfer `git archive` output into `/opt/atlaslm/frontend-releases/<release-id>` as `atlasdeploy`.
4. Confirm the protected env file contains `NEXT_PUBLIC_SUPABASE_URL` and `NEXT_PUBLIC_SUPABASE_ANON_KEY`. Never pass the privileged Supabase service key to the frontend build or container.
5. Run:

   ```bash
   RELEASE_ID=<release-id> scripts/deploy-frontend.sh
   ```

6. Record the immutable Docker image ID and container ID printed by the deployment script.
7. Verify `http://127.0.0.1:3010/login` from the host and through an SSH tunnel before changing DNS.
8. Install `nginx/atlaslm.cloud.http-bootstrap` while the frontend A records still point elsewhere.
9. Change both frontend A records to `212.227.44.13`.
10. Confirm external and server-side DNS propagation, then issue the certificate:

    ```bash
    certbot certonly --webroot -w /var/www/html \
      -d atlaslm.cloud -d www.atlaslm.cloud \
      --agree-tos --non-interactive --email <operations-email>
    ```

11. Replace the bootstrap site with `nginx/atlaslm.cloud`, run `nginx -t`, and reload Nginx.
12. Run the authenticated notebook-to-Report acceptance suite at all required viewports.
13. Verify raw `8080`, Redis, PostgreSQL, Mastra, workers, and internal routes are unreachable externally.
14. Keep the prior Vercel deployment available only as a short rollback path until the self-hosted release is accepted.

## Frontend rollback

Keep the current and previous image tags plus their release directories. Roll back without changing the database:

```bash
scripts/rollback-frontend.sh <known-good-release-id>
```

If DNS was already moved and the self-hosted path cannot be recovered within the rollback window, restore the recorded prior frontend DNS values temporarily. Do not change `api.atlaslm.cloud` during a frontend-only rollback.

## Backend rollback

Use the separately versioned candidate backend release and `scripts/rollback-backend.sh <known-good-release-id>`. The normal code rollback does not restore or rewrite database data. Restore a database backup only for a reviewed data-integrity incident.

## Acceptance and removal of Vercel

Vercel can be disconnected only after all of these pass on `https://www.atlaslm.cloud`:

- normal Supabase SSR authentication;
- notebook creation;
- real source ingestion;
- grounded cited chat and citation opening;
- Report generation, persistence, and reopening;
- cross-workspace isolation;
- retry and idempotency checks;
- desktop, laptop, tablet, and mobile layout evidence;
- TLS, redirect, security-header, and private-port checks;
- tested frontend rollback.

After acceptance, remove the AtlasLM custom domains from Vercel first, observe the self-hosted path, and only then delete obsolete Vercel deployments/project resources. Do not expose secret values in logs, screenshots, image history, Compose files, or shell history.
