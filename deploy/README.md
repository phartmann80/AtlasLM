# AtlasLM dedicated-server staging deployment

Repository changes only. This tree is not installed and does not deploy.

Do not deploy current `main`. Do not change server, DNS, firewall, TLS, production, secrets, or `/etc/atlaslm` permissions. `/etc/atlaslm` is `0700`; `staging.env` and `production.env` are `root:root` `0600`. Leave those permissions unchanged.

Server layout used by the wrapper defaults:

- `/srv/atlaslm/staging` application root (writable by `atlasdeploy`)
- `/srv/atlaslm/releases` immutable SHA trees (writable by `atlasdeploy`)
- `/etc/atlaslm/staging.env` root-owned environment file (not readable by `atlasdeploy`)

## Network model

```
Internet
   │
   ├── staging.atlaslm.cloud
   └── api.staging.atlaslm.cloud
              │
        Caddy :80/:443
              │
       staging proxy network
          ├── frontend:3000
          └── backend:8000
                  │
          private application network
          ├── worker
          ├── mastra:8110
          ├── postgres:5432
          └── redis:6379
```

Only Caddy publishes public host ports. Frontend reaches the backend at `http://backend:8000` through `ATLAS_BACKEND_URL` on the Compose network. Frontend, backend, worker, Mastra, PostgreSQL, and Redis do not publish host ports.

## After this PR is reviewed (not part of the PR)

Populate `/etc/atlaslm/staging.env` as root using the names in `deploy/staging/env.example`. Do not print the file. `NEXT_PUBLIC_*` values must be present at frontend image build time. Never pass `SUPABASE_SERVICE_ROLE_KEY` as a frontend build argument.

Checkout the approved SHA into `/srv/atlaslm/staging` before calling deploy. Do not chmod `/etc/atlaslm`.

### Wrapper installation

```sh
install -o root -g root -m 0750 deploy/atlaslmctl /usr/local/sbin/atlaslmctl
install -o root -g root -m 0440 deploy/sudoers.atlaslm.example /etc/sudoers.d/atlaslm-staging
visudo -cf /etc/sudoers.d/atlaslm-staging
```

### Exact sudoers rule

```
atlasdeploy ALL=(root) NOPASSWD: /usr/local/sbin/atlaslmctl staging deploy *, /usr/local/sbin/atlaslmctl staging rollback *, /usr/local/sbin/atlaslmctl staging status, /usr/local/sbin/atlaslmctl staging logs
```

### Staging deploy

Builds frontend, backend, and Mastra images tagged with the exact 40-character SHA, then starts frontend, backend, worker, Mastra, PostgreSQL, Redis, and Caddy.

```sh
sudo -n /usr/local/sbin/atlaslmctl staging deploy <40-character-sha>
```

### Health checks

Compose healthchecks cover frontend (`:3000`), backend (`/health`), Mastra (`/health`), PostgreSQL (`pg_isready`), Redis (`PING`), worker liveness, and Caddy (`:80`).

```sh
sudo -n /usr/local/sbin/atlaslmctl staging status
curl -fsS https://api.staging.atlaslm.cloud/health
curl -fsS https://staging.atlaslm.cloud/
```

### Rollback

Selects prior immutable image tags. It does not rebuild an old source tree.

```sh
sudo -n /usr/local/sbin/atlaslmctl staging rollback <40-character-sha>
```

### Logs

```sh
sudo -n /usr/local/sbin/atlaslmctl staging logs
```

Production commands, unknown arguments, unapproved Compose files, and non-SHA release IDs are rejected. The wrapper never prints environment-file contents.

## Migrations

`deploy/migrations.manifest.json` is the apply order. `deploy/migrate.py` records checksums in `atlaslm_schema_migrations` and fails atomically per migration. Filename glob order is not used. `010_ai_runtime.down.sql` is excluded.

## Disabled for this staging release

SearXNG, Deep Research, and optional Studio extras are not started.
