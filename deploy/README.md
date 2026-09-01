# AtlasLM dedicated-server staging deployment

Repository changes only. This tree is not installed and does not deploy.

Do not deploy current `main`. Do not change server, DNS, firewall, TLS, production, or `/etc/atlaslm` permissions. `/etc/atlaslm` is `0700`; `staging.env` and `production.env` are `root:root` `0600`. Leave those permissions unchanged.

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

Only Caddy publishes public host ports. Frontend reaches the backend at `http://backend:8000` through `ATLAS_BACKEND_URL` on the Compose network.

## After this PR is reviewed (not part of the PR)

Populate `/etc/atlaslm/staging.env` as root using the names in `deploy/staging/env.example`. Do not print the file. `NEXT_PUBLIC_*` values must be present at frontend image build time. Never pass `SUPABASE_SERVICE_ROLE_KEY` as a frontend build argument.

### Bootstrap / install

```sh
install -o root -g root -m 0750 deploy/atlaslmctl /usr/local/sbin/atlaslmctl
install -o root -g root -m 0440 deploy/sudoers.atlaslm.example /etc/sudoers.d/atlaslm-staging
visudo -cf /etc/sudoers.d/atlaslm-staging
```

Clone or update the reviewed tree at `/srv/atlaslm/repo` if it is not already present. Do not chmod `/etc/atlaslm`.

### Deploy

```sh
sudo -n /usr/local/sbin/atlaslmctl \
  --app-root /srv/atlaslm/repo \
  --env-file /etc/atlaslm/staging.env \
  --project atlaslm-staging \
  --health-url https://api.staging.atlaslm.cloud/health \
  staging deploy <40-character-sha>
```

Images are tagged `atlaslm-staging-{frontend,backend,mastra}:<sha>`. Worker reuses the backend image tag.

### Health checks

Compose healthchecks cover frontend (`:3000`), backend (`/health`), Mastra (`/health`), Postgres (`pg_isready`), Redis (`PING`), worker liveness, and Caddy (`:80`).

After deploy:

```sh
sudo -n /usr/local/sbin/atlaslmctl --app-root /srv/atlaslm/repo --env-file /etc/atlaslm/staging.env staging status
curl -fsS https://api.staging.atlaslm.cloud/health
curl -fsS https://staging.atlaslm.cloud/
```

### Rollback

Selects prior immutable image tags. It does not rebuild an old source tree.

```sh
sudo -n /usr/local/sbin/atlaslmctl \
  --app-root /srv/atlaslm/repo \
  --env-file /etc/atlaslm/staging.env \
  --project atlaslm-staging \
  staging rollback <40-character-sha>
```

### Logs

```sh
sudo -n /usr/local/sbin/atlaslmctl --app-root /srv/atlaslm/repo --env-file /etc/atlaslm/staging.env staging logs
```

Production and unknown arguments are rejected. The wrapper never prints environment-file contents.

## Migrations

`deploy/migrations.manifest.json` is the apply order. `deploy/migrate.py` records checksums in `atlaslm_schema_migrations` and fails atomically per migration. Filename glob order is not used. `010_ai_runtime.down.sql` is excluded.

## Disabled for this staging release

SearXNG, Deep Research, and optional Studio extras are not started.
