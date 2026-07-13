# Authenticated dashboard evidence procedure

Prepared: 2026-07-11

Use this only after the backend candidate is reachable through verified HTTPS and a Vercel Preview points to that backend. Do not use it for Vercel Production until production cutover is approved.

## Authentication rule

Do not add a permanent authentication bypass.

Use one approved path:

- dedicated non-production Supabase test user with normal browser login;
- short-lived preview-only test session;
- manual authenticated browser capture with credentials entered interactively.

Never log, commit, screenshot, or paste:

- email/password pairs;
- access tokens;
- refresh tokens;
- session cookies;
- private source content;
- sensitive traces;
- provider credentials.

## Test data rule

Use only synthetic, non-sensitive test sources.

Recommended source text:

```text
AtlasLM release evidence source. The approved workflow is notebook creation, source ingestion, grounded cited chat, Report generation, and Report reopening after refresh.
```

Do not use real customer, production, private, or personal documents for screenshots.

## Required viewport captures

- `1440 x 900`
- `1366 x 768`
- `1024 x 768`
- `768 x 1024`
- one representative narrow mobile viewport

## Evidence checklist

Each evidence package must show:

- no clipped panels;
- no unintended horizontal overflow;
- visible resize controls;
- mouse resizing;
- keyboard resizing;
- minimum and maximum panel widths;
- collapse and restore;
- layout persistence after refresh;
- Reset layout;
- clear mobile/tablet navigation;
- guided empty states;
- real source status transitions;
- grounded answer and citation interaction;
- generated Report content;
- Report reopening after refresh;
- disabled unfinished modules with clear explanations;
- no enabled action opening an empty modal.

## Capture sequence

1. Open the Vercel Preview URL.
2. Sign in with the dedicated non-production test user.
3. Create a fresh test notebook.
4. Add the synthetic source text.
5. Wait for the source status to reach ready.
6. Ask a grounded question that requires a citation.
7. Open the citation interaction.
8. Generate a Report.
9. Refresh the page and reopen the Report.
10. Exercise resize, keyboard resize, collapse, restore, and Reset layout.
11. Capture each required viewport.
12. Delete the test user/session or revoke it after evidence capture.

