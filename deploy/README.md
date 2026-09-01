# AtlasLM dedicated-server staging deployment

Repository changes only. This tree is not installed and does not deploy.

Do not deploy current `main`. Do not merge, install `atlaslmctl`, install sudoers, populate secrets, or deploy until this PR is independently approved. Do not change server, DNS, firewall, TLS, production, or `/etc/atlaslm` permissions.

## Trust boundary

`atlasdeploy` is unprivileged. It may write only `/srv/atlaslm/incoming`. It must not be able to change anything root later executes.

The installed wrapper runs as root via exact sudoers argv and ignores caller environment, optional flags, repository URLs, Compose paths, health URLs, and project names.

| Path | Owner | atlasdeploy | Used by root wrapper |
| --- | --- | --- | --- |
| `/srv/atlaslm/incoming` | staging upload/request space | writable | never executed |
| `/srv/atlaslm/releases/<sha>` | root:root, not group/world writable | not writable | Compose, Docker build contexts, Caddyfile, `migrate.py`, SQL, Git checkout of that SHA |
| `/srv/atlaslm/runtime/staging` | root-owned symlink into `releases/<sha>` | not writable | status/logs/active release |
| `/usr/local/sbin/atlaslmctl` | root:root `0750` | not writable | installed wrapper |
| `/etc/atlaslm/staging.env` | root:root `0600` | not readable or writable | Compose `--env-file` only; never printed |
| `/etc/atlaslm` | root:root `0700` | cannot inspect | unchanged |

Root obtains the requested commit from the allowlisted remote `https://github.com/phartmann80/AtlasLM.git` into a new `releases/<sha>` directory. The SHA must be 40 lowercase hex characters, a commit object, reachable from `refs/heads/main`, and equal to `git rev-parse HEAD` in that checkout. Symlinks escaping the release root are rejected.

Rollback requires that verified release, requires the SHA-tagged images to already exist, and uses `--no-build --pull never`.

## Network model

Only Caddy publishes public host ports 80/443. Frontend uses `ATLAS_BACKEND_URL=http://backend:8000`. SearXNG, Deep Research, and optional Studio extras are not started.

## Migrations

Order comes from `deploy/migrations.manifest.json`, not filename globs. Apply is atomic **per migration**: one SQL script plus its registry row commit or roll back together. A later failure does not undo earlier successful migrations. Whole-manifest atomicity is not used.

## After independent review (not part of this PR)

Populate `/etc/atlaslm/staging.env` as root. `NEXT_PUBLIC_*` values are required at frontend image build time. Never pass `SUPABASE_SERVICE_ROLE_KEY` as a frontend build argument.

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

atlasdeploy may request only those four commands. It cannot pass `--app-root`, `--env-file`, `--file`, remotes, or health URLs.

### Staging deploy

```sh
sudo -n /usr/local/sbin/atlaslmctl staging deploy <40-character-sha>
```

### Health checks

```sh
sudo -n /usr/local/sbin/atlaslmctl staging status
curl -fsS https://api.staging.atlaslm.cloud/health
curl -fsS https://staging.atlaslm.cloud/
```

### Rollback

```sh
sudo -n /usr/local/sbin/atlaslmctl staging rollback <40-character-sha>
```
