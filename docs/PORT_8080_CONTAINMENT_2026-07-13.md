# AtlasLM current port 8080 exposure assessment

Prepared: 2026-07-13

Scope: immediate assessment of the current live backend exposure on `212.227.44.13:8080` while `api.atlaslm.cloud` is still unresolved.

## Result

Port `8080` remains publicly reachable and is not acceptable as the final production boundary.

It was not fully blocked on 2026-07-13 because the current Vercel `/api/v1/*` proxy is active while `api.atlaslm.cloud` is still NXDOMAIN. Blocking all public inbound traffic to `8080` now would likely break the current live web API path before the candidate backend and TLS path are ready.

## Evidence

External TCP check from the local workstation:

| Port | Result |
| --- | --- |
| `22` | reachable |
| `80` | reachable |
| `443` | reachable |
| `8080` | reachable |
| `5435` | unreachable |
| `6385` | unreachable |
| `8110` | unreachable |
| `8000` | unreachable |
| `3010` | unreachable |

Direct HTTP checks:

- `http://212.227.44.13:8080/health` returns `200`.
- `http://212.227.44.13:8080/internal/atlas/tools/getNotebookContext` returns `401`.
- `http://212.227.44.13:8080/docs` is publicly reachable.
- `http://212.227.44.13:8080/openapi.json` is publicly reachable.

Live frontend/API checks:

- `https://www.atlaslm.cloud/api/v1/health` returns backend-style `401`.
- Browser bundles did not show direct references to `212.227.44.13`, `:8080`, or `api.atlaslm.cloud`.
- The Next.js server-side proxy route uses `ATLAS_BACKEND_URL`, `ATLAS_VERCEL_BACKEND_URL`, or `ATLAS_API_PROXY_TARGET`, which are not visible in browser bundles.
- Since `api.atlaslm.cloud` is unresolved, the working Vercel proxy is treated as likely dependent on the current raw backend endpoint until the candidate release replaces it.

## Temporary containment applied

Observed scanner sources probing paths such as `/manager/html`, `/admin`, and other non-AtlasLM paths were blocked at the Docker firewall boundary with `DOCKER-USER` drop rules.

Current temporary rule marker:

```text
atlaslm-temp-8080-scanner-block
```

Blocked observed scanner sources:

```text
77.22.112.180
94.154.43.140
216.180.246.56
```

These rules do not close the public `8080` exposure. They only reduce active probing from sources already observed in the backend logs. They were chosen because a broad block of `8080` would likely break the current Vercel proxy before DNS/TLS cutover.

## Temporary route hardening applied

Because `8080` must remain temporarily reachable for the current Vercel `/api/v1/*` proxy, public route exposure was reduced with scoped `DOCKER-USER` string-match rules against the current backend container destination.

Current temporary rule marker:

```text
atlaslm-temp-8080-route-hardening
```

Rejected public paths:

```text
/docs
/redoc
/openapi.json
/internal/atlas/*
```

Verification after applying the route-hardening rules:

| Route | Result |
| --- | --- |
| `http://212.227.44.13:8080/health` | still returns `200` |
| `http://212.227.44.13:8080/api/v1/health` | still returns `401` |
| `https://www.atlaslm.cloud/api/v1/health` | still returns `401` |
| `http://212.227.44.13:8080/docs` | rejected before FastAPI |
| `http://212.227.44.13:8080/redoc` | rejected before FastAPI |
| `http://212.227.44.13:8080/openapi.json` | rejected before FastAPI |
| `http://212.227.44.13:8080/internal/atlas/tools/getNotebookContext` | rejected before FastAPI |

This is a temporary containment measure. It is not a substitute for closing public `8080` after the successful `api.atlaslm.cloud` cutover.

## Firewall persistence plan

The temporary `DOCKER-USER` rules are intentionally not made persistent across host reboot.

Reason:

- they are short-term containment while DNS is unresolved;
- final security depends on loopback-binding FastAPI and routing public traffic through Nginx/TLS;
- making temporary string-match rules persistent risks preserving obsolete container IP assumptions after Docker recreates networks.

If the server reboots before cutover, re-assess external `8080` exposure and re-apply only the route-hardening rules that are still necessary. Do not build an unbounded deny list for repeated scanners.

## Scanner rule growth limit

The scanner-specific rules are capped to the observed sources recorded in this document. Do not keep adding one-off scanner IPs as a durable control. If scanning increases, prioritize DNS/TLS cutover and public `8080` closure rather than expanding the deny list.

## Temporary abuse-control posture

Current protections while `8080` remains public:

- authentication is required before workspace, source, chat, Report, ingestion, and generation routes perform user-specific work;
- file upload endpoints enforce a 50 MB application-level upload limit;
- text source ingestion enforces a 2 MB application-level text limit;
- website ingestion truncates fetched HTML content to 10 MB before indexing;
- provider HTTP clients have explicit timeouts and connection limits;
- ingestion and Studio work use Redis queues where available;
- candidate Nginx config has `client_max_body_size 50M` and `proxy_read_timeout 300s`;
- candidate Compose adds service health checks, resource limits, restart policies, and JSON log rotation.

Known temporary limitations:

- the live raw `8080` path is not behind Nginx, so Nginx request-size and timeout controls do not apply until candidate deployment;
- no broad new per-IP rate limit was added because aggressive limits could break the current Vercel proxy path without stable Vercel egress addresses;
- scanner-specific blocking is not a durable security strategy.

## Why not Vercel IP allowlisting yet

Vercel server-side function egress is not safely allowlistable unless the project is configured for Vercel Static IPs or Secure Compute. Vercel documents Static IPs as the feature for fixed outbound IPs used to access backend services that require IP allowlisting.

Until the project has stable Vercel egress IPs or the candidate Nginx/TLS path is deployed, source-IP allowlisting for Vercel would risk breaking the live app.

## Removal after candidate deployment

After the candidate deployment removes public `8080`, remove temporary scanner rules with a reviewed firewall cleanup step. Example pattern:

```bash
iptables -S DOCKER-USER | grep atlaslm-temp-8080-scanner-block
iptables -S DOCKER-USER | grep atlaslm-temp-8080-route-hardening
```

Then delete each matching rule using the corresponding `iptables -D DOCKER-USER ...` form.

## Final required fix

The candidate release must replace the current public binding with:

```text
127.0.0.1:8080:8000
```

Final public boundary passes only after external verification confirms:

- `8080` is no longer publicly reachable;
- Redis, PostgreSQL, Mastra, worker, and internal tool ports are not publicly reachable;
- `/internal/atlas/` is denied at the Nginx public API boundary;
- Vercel Preview reaches the backend through `https://api.atlaslm.cloud`, not the raw IP and port.
