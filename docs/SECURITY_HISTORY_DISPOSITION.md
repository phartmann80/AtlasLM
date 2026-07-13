# AtlasLM security history disposition

Prepared: 2026-07-11

Scope: redacted disposition for the current output of `scripts/secret-scan.ps1 -History` plus the related source review performed during the Mastra notebook-to-report production gate. This document intentionally excludes credential values, token payloads, emails, passwords, and session strings.

Current gate status: production remains unredirected. Current working tree secret scan passes. The owner accepted the classification on 2026-07-11. Git history still requires coordinated cleanup before this repository is made public or broadly shared.

## Current-tree status

- `scripts/secret-scan.ps1` passes for the current working tree.
- `scripts/secret-scan.ps1 -History` reports 108 historical review entries across four file paths.
- The credential-shaped fixtures that caused current-tree risk were removed or changed to environment-driven test inputs.
- Historical Git blobs remain present until a coordinated history rewrite is completed.

## Required owner actions before production cutover

- Revoke any historical user access sessions connected to the authenticated test token finding.
- Confirm whether any refresh token for that user/session existed outside Git. If yes, revoke it.
- Review Vercel Production, Preview, and Development variables after rotation.
- Review the backend server environment file after rotation and restart affected services.
- If the repository is shared, may become public, or contains actual secret material, rewrite history only after rotation/revocation is complete.
- Do not record new secret values in this document, Git, logs, shell history, screenshots, or release reports.

Completion update on 2026-07-11:

- The historical authenticated token reconstructed from Git history identified one affected authenticated user.
- Supabase rejected token-level global sign-out because the historical access token is expired.
- The affected account was confirmed through the service-role admin path as matching disposable test-account signals.
- The affected disposable test account was soft-deleted through the Supabase admin API.
- The soft-deleted record remains visible to admin lookup, which is expected for a soft delete.
- No token value, user id, email address, password, or refresh token value was recorded.

## History finding classification

### 1. `backend/test_rag_pipeline.py`

Commit identifiers reported by the history scanner:

`05b883559a6a`, `0bbf74d8407b`, `0d09190502b9`, `11b24f580a8e`, `11ece5971fc5`, `1a405f7b7711`, `1c56c42fc412`, `27ae37e40e68`, `2a6492ae837c`, `2bfff9b04dff`, `3c2eac69b5a5`, `3c75556801b8`, `3e9e6bcd44e9`, `4366bd4048be`, `45efc6fce238`, `4687e465e4a2`, `4793f5b67c7b`, `4ba02bccd6b5`, `4d47cbbb0a47`, `4d9bce05509d`, `50fe92410e91`, `5831a013e495`, `58eb4e78e261`, `5d18034c16dc`, `5fe4ebcc217d`, `646542f1abab`, `6ba5d7409a2d`, `6c3a9a05d2b2`, `79339b0b9692`, `805dccc7bc22`, `92e77010c280`, `94dc2ab35d9a`, `9a5e0c7aae3a`, `a48b24c4cc32`, `a8306d5a0a23`, `b02db970010e`, `b8df7fb8c3e7`, `c01e312743d6`, `c45cdf42cc3c`, `c4bbda54c223`, `cb419514d9be`, `d05aa2ca245e`, `d31f979df4c8`, `d386a83f7574`, `d6714fa4b515`, `d7301e060614`, `d76377d38f3b`, `d9b7eedb121e`, `db5e9b16c367`, `eb87bb656786`, `ec540c8b2561`, `ed9c2346a1df`, `ee61fd11c643`, `f8f5002005ee`, `ff90af16a202`

Classification:

- Credential category: Supabase authenticated user JWT or authenticated-session-shaped test token.
- Appears to be: real or real-looking user access token material, historically embedded in a test file. Treat as copied once it entered history.
- Expiration status: appears expired from prior metadata review, but expiration is not enough remediation.
- Affected environment: historical local/test API verification and RAG pipeline testing.
- Current remediation: current file no longer embeds the token and reads `ATLAS_TEST_TOKEN` from the environment.
- Required remediation: revoke all sessions for the affected test user, confirm no associated refresh token remains active, and remove or rotate any related test account if needed.
- Rotation/revocation status: completed on 2026-07-11 by soft-deleting the affected disposable test account. Token-level global sign-out was attempted first and rejected by Supabase because the historical access token was expired. No secret values were recorded here.
- Git-history status: still present in historical blobs until a coordinated rewrite is performed.

### 2. `run_api_verification.js`

Commit identifiers reported by the history scanner:

`05b883559a6a`, `0bbf74d8407b`, `0d09190502b9`, `11b24f580a8e`, `1a405f7b7711`, `1c56c42fc412`, `27ae37e40e68`, `2bfff9b04dff`, `3c2eac69b5a5`, `3c75556801b8`, `3e9e6bcd44e9`, `4366bd4048be`, `45efc6fce238`, `4687e465e4a2`, `4793f5b67c7b`, `4ba02bccd6b5`, `4d47cbbb0a47`, `4d9bce05509d`, `50fe92410e91`, `5831a013e495`, `58eb4e78e261`, `5d18034c16dc`, `5fe4ebcc217d`, `6ba5d7409a2d`, `6c3a9a05d2b2`, `805dccc7bc22`, `92e77010c280`, `94dc2ab35d9a`, `9a5e0c7aae3a`, `a48b24c4cc32`, `a8306d5a0a23`, `b02db970010e`, `b8df7fb8c3e7`, `c01e312743d6`, `c45cdf42cc3c`, `c4bbda54c223`, `cb419514d9be`, `d05aa2ca245e`, `d31f979df4c8`, `d386a83f7574`, `d6714fa4b515`, `d7301e060614`, `d76377d38f3b`, `d9b7eedb121e`, `db5e9b16c367`, `eb87bb656786`, `ec540c8b2561`, `ed9c2346a1df`, `ee61fd11c643`, `f8f5002005ee`, `ff90af16a202`

Classification:

- Credential category: Supabase anonymous/public browser key.
- Appears to be: real public anon key material, not a service-role key.
- Expiration status: long-lived public browser credential.
- Affected environment: historical local/frontend API verification configuration.
- Current remediation: current file no longer embeds the key and reads runtime configuration from the environment.
- Required remediation: no service-role rotation is implied by anon-key presence alone. Owner decision on 2026-07-11: do not rotate solely because it appeared in client-generated output. Confirm Row Level Security and authorization policies do not rely on the anon key being secret.
- Rotation/revocation status: not required from this finding.
- Git-history status: still present in historical blobs until a coordinated rewrite is performed.

### 3. `android-shell/android/app/src/main/assets/public/_next/static/chunks/0s41lfpvz6i5x.js`

Commit identifiers reported by the history scanner:

`4366bd4048be`

Classification:

- Credential category: Supabase anonymous/public browser key inside generated static frontend output.
- Appears to be: real public anon key material, not a service-role key.
- Expiration status: long-lived public browser credential.
- Affected environment: historical generated Android shell/static frontend artifact.
- Current remediation: this generated artifact is not present in the current working tree status.
- Required remediation: no service-role rotation is implied by anon-key presence alone. Owner decision on 2026-07-11: do not rotate solely because it appeared in client-generated output. Confirm Row Level Security and authorization policies do not rely on the anon key being secret.
- Rotation/revocation status: not required from this finding.
- Git-history status: still present in historical blobs until a coordinated rewrite is performed.

### 4. `android-shell/android-shell/android/app/src/main/assets/public/_next/static/chunks/0s41lfpvz6i5x.js`

Commit identifiers reported by the history scanner:

`c4bbda54c223`

Classification:

- Credential category: Supabase anonymous/public browser key inside generated static frontend output.
- Appears to be: real public anon key material, not a service-role key.
- Expiration status: long-lived public browser credential.
- Affected environment: historical duplicated generated Android shell/static frontend artifact.
- Current remediation: this generated artifact is not present in the current working tree status.
- Required remediation: no service-role rotation is implied by anon-key presence alone. Owner decision on 2026-07-11: do not rotate solely because it appeared in client-generated output. Confirm Row Level Security and authorization policies do not rely on the anon key being secret.
- Rotation/revocation status: not required from this finding.
- Git-history status: still present in historical blobs until a coordinated rewrite is performed.

## Supplemental review notes

- No tracked private SSH key file was found in the current scanner finding set.
- The Supabase anon key is public/client-side by design and is not equivalent to Supabase service-role exposure.
- No Supabase service-role key, Mastra Gateway key, provider API key, Stripe secret, OAuth client secret, internal signing secret, or private SSH key was confirmed in the current `-History` output.
- Historical database URL/password-like patterns were reviewed separately during hardening. The live production database check indicated production is not using the old historical default password pattern. If that password was ever used outside disposable/local contexts, rotate it anyway before cutover.
- Environment variable names in code and docs are not credential values by themselves; they should stay documented without sample secret values.

## History rewrite decision

History rewriting is recommended if the repository is shared, mirrored, may become public, or will be used by additional contributors.

Before rewriting history:

1. Complete token/session revocation and any approved key rotation.
2. Create a protected backup of the current repository state.
3. Identify all affected refs, tags, branches, and generated artifacts.
4. Purge sensitive historical blobs with a history-rewrite tool.
5. Force-push only after contributor coordination.
6. Invalidate old clones, CI caches, release artifacts, and local generated exports where practical.
7. Re-run `scripts/secret-scan.ps1 -History`.
8. Require contributors to re-clone or hard-reset to the rewritten history.

## Production gate conclusion

Blocker 1 session revocation is complete for the known authenticated-token finding. The repository must remain private while historical credential-shaped material remains in Git history. A coordinated Git-history cleanup is required before the repository is made public or broadly shared.
