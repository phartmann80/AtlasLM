# AtlasLM production environment inventory

Prepared: 2026-07-11

Names, purposes, and supplying party only. Values belong in the approved server secret store, `/etc/atlaslm/atlaslm.env`, Vercel project settings, Supabase, or the relevant provider console. Do not place values in Git, chat, screenshots, shell history, deployment logs, or release reports.

## Backend server env file

Target file: `/etc/atlaslm/atlaslm.env`

Recommended ownership for the accepted deployment model: `root:atlasdeploy`.

Recommended mode for the accepted deployment model: `0640`, because `atlasdeploy` runs routine non-root deployments and must read the Compose env file. The file must not be writable by `atlasdeploy`.

| Variable | Purpose | Supplying party | Production note |
| --- | --- | --- | --- |
| `DB_PASSWORD` | Local Docker Postgres password used by Compose and backend `DATABASE_URL`. | Existing server secret carried forward by DevOps/Codex from the current running deployment. | Must match the existing production DB user password unless the DB password is intentionally rotated. |
| `POSTGRES_USER` | Optional deploy backup user override. | DevOps/Codex default. | Defaults to `atlaslm` when unset. |
| `POSTGRES_DB` | Optional deploy backup database override. | DevOps/Codex default. | Defaults to `atlaslm_db` when unset. |
| `JWT_SECRET` | Fallback application signing secret where legacy paths require it. | DevOps/Codex generated deployment secret if no approved value exists. | Backend-only. |
| `ATLAS_INTERNAL_SIGNING_SECRET` | Short-lived FastAPI-to-Mastra context signing secret. | DevOps/Codex generated deployment secret if no approved value exists. | Backend/Mastra internal only. |
| `ATLAS_PUBLIC_BACKEND_URL` | Public backend origin. | Derived from approved DNS. | Expected production value is the `api.atlaslm.cloud` HTTPS origin after TLS passes. |
| `ATLAS_ALLOWED_ORIGINS` | Browser CORS allowlist. | Paul/domain/Vercel administrator supplies approved production and preview origins; DevOps/Codex formats list. | Must not be wildcard in production. |
| `FRONTEND_URL` | Canonical frontend origin for server-side links/callbacks. | Paul/domain/Vercel administrator. | Use verified production or preview origin depending on release phase. |
| `APP_URL` | Application origin used by invite/share/callback flows. | Paul/domain/Vercel administrator. | Should match the active verified frontend origin for the release phase. |
| `NEXT_PUBLIC_SUPABASE_URL` | Frontend/client Supabase project URL. | Supabase project administrator; currently available through the approved secure local env. | Public client config, not a secret. |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | Frontend/client Supabase anon key. | Supabase project administrator; currently available through the approved secure local env. | Public client config, not a service-role key. |
| `SUPABASE_URL` | Backend Supabase project URL for server-side auth/admin operations. | Supabase project administrator; may mirror `NEXT_PUBLIC_SUPABASE_URL`. | Backend/server use. |
| `SUPABASE_ANON_KEY` | Backend Supabase anon key for auth verification where required. | Supabase project administrator; may mirror `NEXT_PUBLIC_SUPABASE_ANON_KEY`. | Not a privileged secret. |
| `SUPABASE_SERVICE_ROLE_KEY` | Backend-only privileged Supabase admin operations. | Supabase project administrator; currently available through the approved secure local env. | Never expose to frontend or screenshots. |
| `ATLAS_ACTIVE_PROVIDER` | Legacy provider route selector. | DevOps/Codex release setting. | Keep aligned with available provider credentials. |
| `LANGDOCK_API_KEY` | Legacy Langdock credential if used by provider route. | Langdock/project administrator. | Optional if `LANGDOCK_API_CODE` is the active credential form. |
| `LANGDOCK_API_CODE` | Legacy Langdock credential/code if used by provider route. | Langdock/project administrator; currently available through approved secure local env. | Backend-only. |
| `LANGDOCK_ENDPOINT_URL` | Legacy Langdock endpoint. | Langdock/project administrator; currently available through approved secure local env or default. | Backend-only. |
| `LANGDOCK_MODEL` | Legacy Langdock model id. | DevOps/Codex release setting or Langdock/project administrator. | Backend-only. |
| `MODEL` | Legacy model selector used by older provider paths. | DevOps/Codex release setting; currently available through approved secure local env. | Backend-only. |
| `OPENAI_API_KEY` | Optional fallback model provider key. | Provider account administrator. | Leave empty unless explicitly enabled. |
| `OPENROUTER_API_KEY` | Optional fallback model provider key. | Provider account administrator. | Leave empty unless explicitly enabled. |
| `BLACKBOX_API_KEY` | Optional fallback model provider key. | Provider account administrator. | Leave empty unless explicitly enabled. |
| `GEMINI_API_KEY` | Optional fallback model provider key. | Provider account administrator. | Leave empty unless explicitly enabled. |
| `GATEWAY_API_URL` | Mastra Gateway endpoint. | Mastra account administrator; currently available through approved secure local env or default. | Server-only. |
| `GATEWAY_API_MASTRA_KEY` | Mastra Gateway credential. | Mastra account administrator; currently available through approved secure local env. | Server-only privileged credential. |
| `MASTRA_MODEL` | Mastra model id. | DevOps/Codex release setting. | Keep stable for notebook-to-report acceptance. |
| `MASTRA_INTERNAL_URL` | Private FastAPI-to-Mastra URL. | DevOps/Codex release setting. | Should remain private Docker network URL in production. |
| `ATLAS_API_URL` | Private Mastra-to-FastAPI URL. | DevOps/Codex release setting. | Should remain private Docker network URL in production. |
| `ATLAS_CHAT_RUNTIME` | Chat runtime switch. | DevOps/Codex release setting. | Keep scoped to approved notebook-to-report release. |
| `ATLAS_REPORT_RUNTIME` | Report runtime switch. | DevOps/Codex release setting. | Set to Mastra only for the approved Report workflow. |
| `ATLAS_RESEARCH_RUNTIME` | Research runtime switch. | DevOps/Codex release setting. | Keep legacy/off until Research Interest Agent is approved. |
| `ATLAS_MEMORY_MODE` | Memory behavior switch. | DevOps/Codex release setting. | Initial production value should remain conservative. |
| `ATLAS_TRACE_CONTENT` | Trace content privacy setting. | DevOps/Codex release setting. | Keep redacted for production. |
| `ATLAS_ENV` | Runtime environment label. | DevOps/Codex release setting. | Use production label only for production cutover. |
| `RESEARCH_HTTP_TIMEOUT` | Research/web fetch timeout. | DevOps/Codex release setting. | Must not be blank. |
| `AUDIO_DIR` | Audio output storage path. | DevOps/Codex release setting. | Audio Overview remains disabled until approved. |
| `ATLAS_TTS_BIN` | TTS binary path. | DevOps/Codex release setting. | Audio Overview remains disabled until approved. |
| `ATLAS_VOICE_A` | TTS voice file path. | DevOps/Codex release setting. | Audio Overview remains disabled until approved. |
| `ATLAS_VOICE_B` | TTS voice file path. | DevOps/Codex release setting. | Audio Overview remains disabled until approved. |
| `STRIPE_WEBHOOK_SECRET` | Stripe webhook verification. | Stripe account administrator. | Leave empty unless billing webhooks are active. |
| `SEARXNG_URL` | Private SearXNG/research search URL. | DevOps/Codex or infrastructure administrator. | Research remains gated. |
| `SEARXNG_SECRET` | Private SearXNG secret. | DevOps/Codex or infrastructure administrator. | Required only if SearXNG service is enabled. |
| `ATLAS_GOOGLE_CLIENT_ID` | Google integration OAuth client id. | Google Cloud/project administrator. | Google Docs/Slides integration requires review before production use. |
| `ATLAS_GOOGLE_CLIENT_SECRET` | Google integration OAuth client secret. | Google Cloud/project administrator. | Server-only privileged credential. |
| `ATLAS_GOOGLE_REDIRECT_URI` | Google OAuth redirect URI. | Google Cloud/project administrator with domain/Vercel administrator. | Must match deployed verified origin. |
| `ATLAS_GOOGLE_PROJECT_NUMBER` | Google Picker/project number. | Google Cloud/project administrator. | Required for Picker only. |
| `ATLAS_GOOGLE_PICKER_API_KEY` | Google Picker browser key. | Google Cloud/project administrator. | Client-facing key, restrict by origin. |
| `ATLAS_VAULT_KEY` | Encrypted connection-token storage key. | DevOps/Codex generated deployment secret or security owner. | Required before storing connected-account tokens. |
| `ATLAS_VAULT_KEY_ID` | Vault key version id. | DevOps/Codex release setting. | Rotate when `ATLAS_VAULT_KEY` rotates. |
| `ATLAS_WEBHOOK_URL` | Internal webhook target. | Infrastructure/application owner. | Leave empty unless webhooks are active. |
| `ATLAS_WATCH_SWEEP_SECONDS` | Google/live sync sweep interval. | DevOps/Codex release setting. | Default is acceptable unless load testing says otherwise. |
| `ATLAS_WATCH_RENEW_WITHIN` | Google/live sync renewal window. | DevOps/Codex release setting. | Default is acceptable unless load testing says otherwise. |
| `ATLAS_INVITE_TTL_SECONDS` | Invite expiry window. | DevOps/Codex release setting. | Default is acceptable unless policy changes. |
| `ATLAS_DEFAULT_SEAT_LIMIT` | Default workspace seat limit. | Product owner/DevOps release setting. | Keep conservative until billing/team flows are accepted. |
| `NEXT_PUBLIC_API_BASE` | Frontend API base for containerized frontend or preview builds. | Derived from verified backend hostname by DevOps/Codex. | Vercel Preview uses project settings, not the server env file. |
| `NEXT_PUBLIC_API_URL` | Legacy frontend API base fallback. | Derived from verified backend hostname by DevOps/Codex. | Prefer `NEXT_PUBLIC_API_BASE` for new configuration. |

## Vercel project variables

These are not installed in `/etc/atlaslm/atlaslm.env`; they belong in Vercel environment settings.

| Variable | Purpose | Supplying party | Production note |
| --- | --- | --- | --- |
| `NEXT_PUBLIC_SUPABASE_URL` | Client Supabase project URL. | Supabase project administrator. | Public client config. |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | Client Supabase anon key. | Supabase project administrator. | Public client config; do not treat as service-role. |
| `NEXT_PUBLIC_API_BASE` | Browser API base. | DevOps/Codex after TLS smoke passes. | Do not point Production to `api.atlaslm.cloud` until backend smoke and dashboard evidence pass. |
| `NEXT_PUBLIC_API_URL` | Legacy browser API base fallback. | DevOps/Codex after TLS smoke passes. | Keep aligned with `NEXT_PUBLIC_API_BASE` if used. |
| `ATLAS_BACKEND_URL` | Next.js server-side API proxy target. | DevOps/Codex after TLS smoke passes. | Preview may point to `https://api.atlaslm.cloud`; Production waits for final approval. |
| `ATLAS_VERCEL_BACKEND_URL` | Alternate server-side API proxy target. | DevOps/Codex after TLS smoke passes. | Optional fallback. |
| `ATLAS_API_PROXY_TARGET` | Alternate server-side API proxy target. | DevOps/Codex after TLS smoke passes. | Optional fallback. |
| `NEXT_PUBLIC_DEFAULT_SEAT_LIMIT` | Client-visible default workspace seat limit. | Product owner/DevOps release setting. | Optional. |

## Deployment-only variables

These are supplied at command time or through the deployment shell environment, not committed.

| Variable | Purpose | Supplying party | Production note |
| --- | --- | --- | --- |
| `APP_ROOT` | Deployment root. | DevOps/Codex release command. | Defaults to `/opt/atlaslm`. |
| `SOURCE_DIR` | Local source checkout used by deploy script. | DevOps/Codex release command. | Defaults to current directory. |
| `RELEASE_ID` | Versioned release identifier. | DevOps/Codex release command. | Should tie to Git commit or immutable image tag. |
| `ENV_FILE` | Compose env file path. | DevOps/Codex release command. | Defaults to `/etc/atlaslm/atlaslm.env`. |
| `BACKUP_DIR` | Backup output directory. | DevOps/Codex release command. | Defaults to `/var/backups/atlaslm`. |
| `ALLOW_ROOT_DEPLOY` | Emergency override for root deployment. | DevOps/Codex only with explicit approval. | Routine deployment should not set this. |
| `ATLAS_ACCEPTANCE_API_BASE` | Acceptance smoke API base. | DevOps/Codex release command. | Use preview/staging/prod backend as appropriate. |
| `ATLAS_ACCEPTANCE_TOKEN_A` | Acceptance test user A access token. | DevOps/Codex generated short-lived test session. | Never log or commit. |
| `ATLAS_ACCEPTANCE_TOKEN_B` | Acceptance test user B access token. | DevOps/Codex generated short-lived test session. | Never log or commit. |
| `REQUIRE_ATLAS_ACCEPTANCE` | CI/test failure mode. | DevOps/Codex release command. | Set to `1` only when secure tokens are present. |
| `ATLAS_PUBLIC_BACKEND_URL` | Production smoke backend origin override. | DevOps/Codex release command. | Used by smoke scripts. |

