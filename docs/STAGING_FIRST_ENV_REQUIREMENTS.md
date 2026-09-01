# First staging environment requirements

Repository and configuration review only. This document does not deploy, does not
populate `/etc/atlaslm/staging.env`, and does not change DNS, firewall, Caddy,
TLS, permissions, or production.

Do not print or paste secret values into git, chat, screenshots, or shell history.
Paul fills `/etc/atlaslm/staging.env` as root on the server. Then:

```sh
python3 deploy/validate_staging_env.py /etc/atlaslm/staging.env
```

The validator reports only `SET`, `EMPTY`, `MISSING`, `VALID_FORMAT`, or
`INVALID_FORMAT`. It never prints values, lengths of sensitive values, prefixes,
suffixes, hashes, or derived identifiers.

Production and mobile remain blocked.

## Selected first-staging choices

- AI provider: Langdock
- Stripe: test mode, webhooks not required for the first acceptance suite
- Dedicated non-production Supabase project: required; current status unknown
- Non-production Mastra gateway: not required for the first acceptance suite

## 1. Supabase

### Hosted project plus local Postgres

AtlasLM requires **both**:

1. A **hosted Supabase project** for Auth (JWT issuance and JWKS) and the
   `public.profiles` table (PostgREST).
2. The **staging PostgreSQL container** in `deploy/staging/docker-compose.yaml`
   (`postgres`, database `atlaslm_db`, volume `atlaslm_staging_pgdata`) for
   notebooks, sources, chunks, jobs, and related application tables.

These are different databases. `DATABASE_URL` in staging Compose always points at
the local container: `postgresql://atlaslm:${DB_PASSWORD}@postgres:5432/atlaslm_db`.
The hosted Supabase Postgres is **not** the Compose database and must **not**
receive `deploy/migrate.py`.

### Required Supabase features

| Feature | Required for first staging | How AtlasLM uses it |
| --- | --- | --- |
| Auth | Yes | Email/password login and signup, dashboard session cookies, backend JWT verification via `/auth/v1/.well-known/jwks.json` |
| Database / PostgREST `profiles` | Recommended | Frontend `profiles` read; Stripe webhook writes `tier` and `stripe_customer_id`. Not required for `scripts/acceptance-matrix.js` |
| Storage | No | No `storage.from` usage in the product paths reviewed |
| Realtime | No | Not used |
| Edge Functions | No | Not used |

Backend application data (workspaces, documents, embeddings, reports) lives in
the **local staging PostgreSQL container**, not hosted Supabase.

### Documented staging project identifier

No dedicated staging project URL is documented in `deploy/staging/env.example`
or `docs/ENVIRONMENT_INVENTORY.md`. Those files leave `NEXT_PUBLIC_SUPABASE_URL`
empty.

### Non-secret metadata already in this repository

A public Supabase hostname appears as a **fallback default** in
`run_api_verification.py` and as a localStorage key prefix in screenshot helper
scripts: `https://ortmzzdfkwidvuolczqa.supabase.co`.

That host is public project metadata, not a secret. It is **not** labeled as a
dedicated non-production staging project. Do not assume it is safe to reuse for
`staging.atlaslm.cloud`. Paul should identify it in the Supabase dashboard by
the public URL only, then create or select a **dedicated** non-production
project for staging.

Do not paste the service role key, database password, or JWT secret from any
existing project into chat.

### Safe dashboard steps to create or identify a dedicated non-production project

Perform these in the Supabase dashboard. Copy secrets only into
`/etc/atlaslm/staging.env` on the server as root.

1. Sign in at the Supabase dashboard.
2. In the project list, identify existing projects by **name**, **region**, and
   the public API URL (`https://<project-ref>.supabase.co` under Project Settings
   then API). Compare that public URL with production and with the repository
   fallback host above. Do not open the service-role panel yet.
3. If no dedicated non-production project exists, choose New project.
   - Name it so production is obvious by contrast (for example `atlaslm-staging`).
   - Region: prefer an EU region close to the dedicated server (`ubuntu` /
     `85.215.156.241`).
   - Let the dashboard generate the **hosted** database password. That password
     is for hosted Supabase Postgres only. It is **not** `DB_PASSWORD` in
     staging.env. `DB_PASSWORD` is for the local Docker Postgres container.
   - Wait until the project is healthy.
4. Project Settings then API. Current projects show two key generations. Use one complete pair; do not mix a production project into staging.

   **Current API Keys panel** (preferred when present):
   - Copy the **Publishable** key into `NEXT_PUBLIC_SUPABASE_ANON_KEY`.
   - Copy the **Secret** key into `SUPABASE_SERVICE_ROLE_KEY` on the server only.

   **Legacy JWT panel** (still valid on older projects):
   - Copy the `anon` `public` JWT into `NEXT_PUBLIC_SUPABASE_ANON_KEY`.
   - Copy the `service_role` JWT into `SUPABASE_SERVICE_ROLE_KEY` on the server only.

   Never put a Secret key or a `service_role` JWT into any `NEXT_PUBLIC_*` name, frontend build arg, git, or chat.
   Copy `Project URL` into `NEXT_PUBLIC_SUPABASE_URL` (Compose maps `SUPABASE_URL` from that name).
5. Do not enable the project as production. Do not attach production custom
   domains.

### Redirect URLs, site URL, origins, buckets, providers

Configure Authentication then URL Configuration on the **staging** project:

- **Site URL:** `https://staging.atlaslm.cloud`
- **Redirect URLs:**
  - `https://staging.atlaslm.cloud/auth/callback`
  - `https://staging.atlaslm.cloud/auth/callback?redirect_origin=https://staging.atlaslm.cloud`
- Do not add `https://www.atlaslm.cloud`, `https://atlaslm.cloud`, or
  `https://atlaslm.vercel.app` to the staging project.
- Localhost redirect URLs are not required for server staging.

Allowed browser origin for AtlasLM CORS (Compose / `ATLAS_ALLOWED_ORIGINS`):

- `https://staging.atlaslm.cloud`

Storage buckets: none required.

Authentication providers:

- **Email:** enable. For first staging, disable "Confirm email" unless staging
  SMTP is already configured. First acceptance uses password login and issued
  access tokens, not mailbox proof.
- **Google / GitHub:** present in the login UI but **not** required for
  `scripts/acceptance-matrix.js`. Leave them disabled on the staging project
  until separate OAuth clients exist. Do not reuse production OAuth clients.
- **Phone / SAML / SSO:** leave disabled.

Recommended hosted SQL (run in the staging project's SQL editor, not through
`deploy/migrate.py`):

```sql
create table if not exists public.profiles (
  id uuid primary key references auth.users (id) on delete cascade,
  email text,
  full_name text,
  tier text not null default 'Free',
  stripe_customer_id text unique,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

alter table public.profiles enable row level security;

drop policy if exists profiles_select_own on public.profiles;
create policy profiles_select_own
  on public.profiles
  for select
  using (auth.uid() = id);

create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
  insert into public.profiles (id, email)
  values (new.id, new.email)
  on conflict (id) do nothing;
  return new;
end;
$$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
  after insert on auth.users
  for each row execute procedure public.handle_new_user();
```

Service role (used by the Stripe webhook) bypasses RLS. The first acceptance
suite does not require this table.

### Which database receives the migration manifest

`deploy/migrate.py` applies `deploy/migrations.manifest.json` to the **local
staging PostgreSQL container** using the backend container's `DATABASE_URL`.
`atlaslmctl staging deploy` runs that migrator against that URL only.

Do not point `DATABASE_URL` at hosted Supabase. Do not run the manifest against
hosted Supabase. Hosted Auth schema is managed by Supabase.

## 2. Langdock

Active integration is `backend/app/core/providers.py`. The registry treats
Langdock as an OpenAI-compatible provider.

### Variables

| Name | Required | Role |
| --- | --- | --- |
| `ATLAS_ACTIVE_PROVIDER` | Yes | Must be `langdock` for this staging choice |
| `LANGDOCK_API_CODE` | One of code or key | Preferred credential. Used first when both are set |
| `LANGDOCK_API_KEY` | One of code or key | Used when `LANGDOCK_API_CODE` is empty |
| `LANGDOCK_ENDPOINT_URL` | Yes | OpenAI-compatible base URL |
| `LANGDOCK_MODEL` | Yes | Chat/completions model id |
| `LANGDOCK_WORKSPACE_ID` | No | Declared in settings, unused by the provider registry. Leave absent/empty |
| `MODEL` | No | Legacy alias. `LANGDOCK_MODEL` wins. Leave empty |

`LANGDOCK_API_KEY`, `LANGDOCK_API_CODE`, or **both** may be set. **At least one**
must be set. If both are set, `LANGDOCK_API_CODE` is the credential that is used.
Do not print either value.

### Endpoint URL format

Exact allowed values for first staging:

- `https://api.langdock.com/openai/eu/v1` (code default; preferred if the
  Langdock workspace is EU)
- `https://api.langdock.com/openai/us/v1`

No trailing slash. No extra path. HTTPS only.

### Supported model value for the first staging test

Use `gpt-5-mini`. That is the backend default and the value
`normalize_model_name` falls back to. Embeddings are hardcoded to
`text-embedding-ada-002` on the same Langdock endpoint. The Langdock workspace
must allow both that chat model and that embedding model.

### Separate / restricted credential

Yes. Use a staging-only Langdock credential with the least usable quota. Do not
reuse the production credential. Do not put the value in git or chat.

## 3. Mastra

### Mandatory for the first staging acceptance suite?

**The Mastra container is still started.** `atlaslmctl` always builds and starts
`mastra`. Compose health for Mastra remains `GET /health` and is unchanged.

**Mastra is not used for first staging chat, report, or research.** Compose and
`deploy/staging/env.example` keep:

- `ATLAS_CHAT_RUNTIME=legacy`
- `ATLAS_REPORT_RUNTIME=legacy`
- `ATLAS_RESEARCH_RUNTIME=legacy`
- `ATLAS_MEMORY_MODE=off`

`scripts/acceptance-matrix.js` exercises notebook, ingest, grounded chat, and
report through the FastAPI legacy runtime. It does not call Mastra.

### `GATEWAY_API_URL` and `GATEWAY_API_MASTRA_KEY` with legacy runtimes

Not required. Leave both empty for first staging.

If one is set, both must be set. Do not set them to the production Mastra
gateway.

### Can Mastra start and remain healthy with those values empty?

Yes. `GET /health` returns `{ status: "healthy", service: "mastra" }` without
calling the gateway. This PR stops the previous source default that pointed an
empty `GATEWAY_API_URL` at the production Mastra gateway. Empty now fails closed
against `http://127.0.0.1:9/v1` if generate is accidentally invoked.

### `MASTRA_MODEL` when Langdock is the selected provider

Leave `MASTRA_MODEL` empty. Mastra does not speak Langdock. It uses an
OpenAI-compatible Mastra gateway. Langdock model ids are not valid Mastra
gateway model ids. The unused empty value is correct while runtimes stay
`legacy`.

### Recommendation

**B, scoped:** keep the Mastra **service** and its `/health` check. Make the
**gateway** optional for first staging.

Do not remove Mastra from Compose or skip its healthcheck. Do not weaken
existing health checks.

A valid non-production gateway (option A) can be added later without a further
Compose change: set `GATEWAY_API_URL` and `GATEWAY_API_MASTRA_KEY` together, then
change runtime flags only after that gateway is reviewed.

## 4. Stripe test mode

### Needed for the initial staging acceptance suite?

No. `scripts/acceptance-matrix.js` does not create checkouts or send webhooks.
The webhook handler fails closed when `STRIPE_WEBHOOK_SECRET` is empty, which is
correct. Leave `STRIPE_WEBHOOK_SECRET` empty for first staging.

### Endpoint URL (when Paul later enables test webhooks)

`https://api.staging.atlaslm.cloud/stripe/webhook`

That is FastAPI `POST /stripe/webhook` behind Caddy on `api.staging.atlaslm.cloud`.
The route is already excluded from JWT auth.

### Required test-mode events

The handler acts on:

- `checkout.session.completed`
- `customer.subscription.updated`
- `customer.subscription.deleted`

Other event types are acknowledged and ignored.

### How Paul obtains the test signing secret

In the Stripe Dashboard, turn **Test mode** on. Open Developers then Webhooks.
Add an endpoint with the URL above and the three events. Open that endpoint and
reveal **Signing secret**. Copy it only into `/etc/atlaslm/staging.env` as
`STRIPE_WEBHOOK_SECRET`. Never paste it into git or chat.

Do not use a live-mode signing secret on staging.

## 5. Secret generation and classification

| Variable | Classification | First-staging value / rule |
| --- | --- | --- |
| `ATLAS_RELEASE_SHA` | Automatically set by atlaslmctl | Leave empty in staging.env |
| `NEXT_PUBLIC_API_BASE` | Fixed non-secret staging value | `/api/v1` |
| `STAGING_FRONTEND_HOST` | Fixed non-secret staging value | `staging.atlaslm.cloud` |
| `STAGING_API_HOST` | Fixed non-secret staging value | `api.staging.atlaslm.cloud` |
| `FRONTEND_URL` | Fixed non-secret staging value | `https://staging.atlaslm.cloud` |
| `APP_URL` | Fixed non-secret staging value | `https://staging.atlaslm.cloud` |
| `ATLAS_PUBLIC_BACKEND_URL` | Fixed non-secret staging value | `https://api.staging.atlaslm.cloud` |
| `ATLAS_ALLOWED_ORIGINS` | Fixed non-secret staging value | `https://staging.atlaslm.cloud` |
| `ATLAS_ENV` | Fixed non-secret staging value | `staging` |
| `ATLAS_VAULT_KEY_ID` | Fixed non-secret staging value | `v1` |
| `ATLAS_ACTIVE_PROVIDER` | Fixed non-secret staging value | `langdock` |
| `LANGDOCK_ENDPOINT_URL` | Retrieve from Langdock (non-secret URL) | `https://api.langdock.com/openai/eu/v1` unless the workspace is US |
| `LANGDOCK_MODEL` | Retrieve from Langdock / release setting | `gpt-5-mini` |
| `ATLAS_CHAT_RUNTIME` | Fixed non-secret staging value | `legacy` |
| `ATLAS_REPORT_RUNTIME` | Fixed non-secret staging value | `legacy` |
| `ATLAS_RESEARCH_RUNTIME` | Fixed non-secret staging value | `legacy` |
| `ATLAS_MEMORY_MODE` | Fixed non-secret staging value | `off` |
| `ATLAS_TRACE_CONTENT` | Fixed non-secret staging value | `redacted` |
| `RESEARCH_HTTP_TIMEOUT` | Fixed non-secret staging value | `12` |
| `ATLAS_DEFAULT_SEAT_LIMIT` | Fixed non-secret staging value | `5` |
| `DB_PASSWORD` | Generate securely on the server | See generation notes |
| `JWT_SECRET` | Generate securely on the server | See generation notes |
| `ATLAS_INTERNAL_SIGNING_SECRET` | Generate securely on the server | See generation notes |
| `ATLAS_VAULT_KEY` | Generate securely on the server | See generation notes |
| `NEXT_PUBLIC_SUPABASE_URL` | Retrieve from Supabase | Public project URL |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | Retrieve from Supabase | Publishable key from the current API Keys panel, or legacy `anon` `public` JWT |
| `SUPABASE_SERVICE_ROLE_KEY` | Retrieve from Supabase | Secret key from the current API Keys panel, or legacy `service_role` JWT. Backend only. |
| `LANGDOCK_API_KEY` | Retrieve from Langdock | Optional if `LANGDOCK_API_CODE` is set |
| `LANGDOCK_API_CODE` | Retrieve from Langdock | Preferred if present |
| `STRIPE_WEBHOOK_SECRET` | Retrieve from Stripe test mode | Optional; leave empty for first staging |
| `GATEWAY_API_URL` | Retrieve from the Mastra gateway | Optional; leave empty for first staging |
| `GATEWAY_API_MASTRA_KEY` | Retrieve from the Mastra gateway | Optional; leave empty for first staging |
| `MASTRA_MODEL` | Optional and leave empty | Empty while runtimes are legacy |
| `MODEL` | Optional and leave empty | Empty |
| `BLACKBOX_API_KEY` | Optional and leave empty | Empty |
| `OPENROUTER_API_KEY` | Optional and leave empty | Empty |
| `OPENAI_API_KEY` | Optional and leave empty | Empty |
| `GEMINI_API_KEY` | Optional and leave empty | Empty |

Compose also interpolates `SUPABASE_URL` and `SUPABASE_ANON_KEY` from the
`NEXT_PUBLIC_*` names. Do not add duplicate keys.

`ATLAS_BACKEND_URL` and `MASTRA_INTERNAL_URL` are hardcoded in Compose to the
private Docker network. Do not put them in staging.env.

### Generated secrets

Run these **on the server as root**. Do not paste the output into chat.

```sh
openssl rand -hex 32      # DB_PASSWORD only. URI-safe. 32 bytes.
openssl rand -base64 48   # JWT_SECRET
openssl rand -base64 48   # ATLAS_INTERNAL_SIGNING_SECRET
openssl rand -base64 32   # ATLAS_VAULT_KEY
```

Do not generate `DB_PASSWORD` with Base64. Compose interpolates it unescaped into
`postgresql://atlaslm:${DB_PASSWORD}@postgres:5432/atlaslm_db`. Standard Base64
may contain `/`, which splits userinfo and silently yields an invalid
`DATABASE_URL`. Hex from `openssl rand -hex 32` is 64 lowercase hex characters
and round-trips in that URI. `JWT_SECRET`, `ATLAS_INTERNAL_SIGNING_SECRET`, and
`ATLAS_VAULT_KEY` are not embedded in that URI, so they may remain Base64.

| Secret | Encoding | Minimum entropy | Later rotation |
| --- | --- | --- | --- |
| `DB_PASSWORD` | lowercase hex, 64 characters (`openssl rand -hex 32`) | 32 bytes | Changing it without `ALTER USER` on the existing volume breaks Postgres auth. First deploy generates once. |
| `JWT_SECRET` | UTF-8; CSPRNG base64 is fine | 32 bytes | Required to boot Settings. No session-signing use was found; Supabase JWTs are independent. Rotation should not invalidate Auth sessions today. |
| `ATLAS_INTERNAL_SIGNING_SECRET` | UTF-8; HMAC-SHA256 key | 32 bytes | Generate even though Mastra runtimes stay legacy, because the Mastra container is started. Rotation invalidates in-flight internal requests (TTL 120 seconds). |
| `ATLAS_VAULT_KEY` | Any UTF-8 secret; SHA-256 then urlsafe-base64 Fernet key | 32 bytes | Rotation invalidates stored connected-account refresh tokens. Google connections are not part of first acceptance. |

Do not use `/dev/urandom` output in chat logs. Redirect into the env file on the
server only.

## 6. Validation

```sh
python3 deploy/validate_staging_env.py /etc/atlaslm/staging.env
```

Exit `0` only when required first-staging fields are `SET` with `VALID_FORMAT`
and optional fields are `EMPTY` or `SET` with `VALID_FORMAT`. Exit `1` on format
or missing required values. Exit `2` if the file cannot be read.

The script never prints values. It also rejects:

- a `service_role` JWT or a Secret API key in `NEXT_PUBLIC_SUPABASE_ANON_KEY` or any other `NEXT_PUBLIC_*` name
- a Publishable key or `anon` JWT in `SUPABASE_SERVICE_ROLE_KEY`
- a `DB_PASSWORD` that is not 64 lowercase hex characters, including standard Base64
- a production Mastra gateway URL
- a gateway URL without a matching gateway key (or the reverse)
- both Langdock credential names empty

It accepts either current API Keys (`Publishable` + `Secret`) or legacy JWTs
(`anon` `public` + `service_role`), including mixed pairs from the same
non-production project.

## 7. Deployment SHA

Do **not** deploy `6085582c8dc4d7dba656c3a95109365145229dd7`. That commit is the
reviewed PR #7 tree only. It does not contain this PR's Mastra fail-closed
change, validator, documentation, or tests. The fact that the installed
`atlaslmctl` wrapper was copied from that SHA does not make it the application
release SHA.

The first staging **application** SHA must be a commit on `refs/heads/main` that
contains both:

- the reviewed PR #7 staging hardening
- the reviewed PR #8 configuration review (this change)

That is the **merge commit** created when this PR is merged into `main` with a
normal merge commit, not a squash. Do not treat the reviewed PR head as the
deploy SHA.

After that merge, the fail-closed proof is:

```sh
git fetch origin main
MAIN_SHA="$(git rev-parse origin/main)"
test "$(printf '%s' "$MAIN_SHA" | grep -E '^[0-9a-f]{40}$')" = "$MAIN_SHA"
git merge-base --is-ancestor ceb03f26fd5482aa0bbe33b2dbb5bb89a0d84d66 origin/main
git merge-base --is-ancestor 6085582c8dc4d7dba656c3a95109365145229dd7 origin/main
printf 'MAIN_SHA=%s\n' "$MAIN_SHA"
```

`ceb03f26fd5482aa0bbe33b2dbb5bb89a0d84d66` is the reviewed PR #8 head used only
for the ancestry proof (the revision that resolved the three substantive
blockers). `6085582c8dc4d7dba656c3a95109365145229dd7` is the reviewed PR #7
commit. Neither is the deployment SHA.

The first-staging candidate is the normal merge commit reported by
`git rev-parse origin/main` after this sequence exits 0.

Until that merge exists, there is no approved first-staging deploy SHA. Do not
deploy in this PR.

## Out of scope

- Do not access the dedicated server from this PR
- Do not populate `/etc/atlaslm/staging.env` from git
- Do not deploy
- Do not change DNS, firewall, Caddy, TLS, production, or permissions
- Do not start Android or iOS work
