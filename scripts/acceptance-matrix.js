/*
 * Authenticated notebook-to-report acceptance matrix.
 *
 * It intentionally requires two separately issued Supabase access tokens.
 * Tokens are read from the environment and never printed. Set
 * REQUIRE_ATLAS_ACCEPTANCE=1 in CI to turn missing credentials into a hard
 * failure; local runs skip cleanly when the secure test credentials are absent.
 */

const base = (process.env.ATLAS_ACCEPTANCE_API_BASE || "https://api.atlaslm.cloud/api/v1").replace(/\/$/, "");
const tokenA = process.env.ATLAS_ACCEPTANCE_TOKEN_A;
const tokenB = process.env.ATLAS_ACCEPTANCE_TOKEN_B;

if (!tokenA || !tokenB) {
  const message = "acceptance matrix: SKIP, two secure test tokens are not configured";
  if (process.env.REQUIRE_ATLAS_ACCEPTANCE === "1") {
    console.error(message);
    process.exit(2);
  }
  console.log(message);
  process.exit(0);
}

async function request(path, token, options = {}) {
  const response = await fetch(`${base}${path}`, {
    ...options,
    headers: {
      Authorization: `Bearer ${token}`,
      ...(options.body instanceof FormData ? {} : { "content-type": "application/json" }),
      ...(options.headers || {}),
    },
  });
  const text = await response.text();
  let body = text;
  try { body = text ? JSON.parse(text) : null; } catch { /* keep text */ }
  return { response, body };
}

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

async function json(path, token, method, body) {
  const result = await request(path, token, { method, body: JSON.stringify(body) });
  assert(result.response.ok, `${method} ${path} returned ${result.response.status}`);
  return result.body;
}

const suffix = `acceptance-${Date.now()}`;
const workspaceA = await json("/workspaces", tokenA, "POST", { name: `${suffix}-A` });
const workspaceB = await json("/workspaces", tokenB, "POST", { name: `${suffix}-B` });
const source = await json(`/workspaces/${workspaceA.id}/documents/text`, tokenA, "POST", {
  title: "Acceptance source",
  content: "Atlas acceptance evidence: the notebook source says the approved workflow is notebook, source, ingestion, grounded answer, and report.",
});

let status = "pending";
for (let attempt = 0; attempt < 30; attempt += 1) {
  const result = await request(`/documents/${source.id}/status`, tokenA, { method: "GET" });
  assert(result.response.ok, "source status endpoint failed");
  status = result.body.status;
  if (status === "ready" || status === "failed") break;
  await new Promise((resolve) => setTimeout(resolve, 1000));
}
assert(status === "ready", `source did not become ready, status=${status}`);

const session = await json(`/workspaces/${workspaceA.id}/sessions`, tokenA, "POST", { title: "Acceptance chat" });
const chat = await request(`/sessions/${session.id}/chat/stream`, tokenA, {
  method: "POST",
  body: JSON.stringify({ content: "What does the acceptance source say?", mode: "sources" }),
});
assert(chat.response.ok, "grounded chat request failed");
assert(chat.body.includes("event: metadata"), "grounded chat did not stream metadata");
assert(chat.body.includes("source_"), "grounded chat did not return a citation reference");

const report = await json(`/workspaces/${workspaceA.id}/studio`, tokenA, "POST", {
  output_type: "report",
  title: "Acceptance Report",
  source_ids: [source.id],
  length: "brief",
  focus: "Summarize the approved workflow",
  idempotency_key: `${suffix}-report`,
});
assert(report.status === "ready", `report did not become ready, status=${report.status}`);
assert(report.content, "report content was empty");
assert(Array.isArray(report.citations) && report.citations.length > 0, "report citations were not persisted");

const reopened = await request(`/workspaces/${workspaceA.id}/studio/${report.id}`, tokenA, { method: "GET" });
assert(reopened.response.ok && reopened.body.content, "report did not reopen after persistence");

const deniedSource = await request(`/workspaces/${workspaceA.id}/documents`, tokenB, { method: "GET" });
assert(deniedSource.response.status === 404, "cross-workspace source access was not denied");
const layout = await json(`/workspaces/${workspaceA.id}/layout`, tokenA, "PUT", { layout: { source_panel_width: 400, output_panel_width: 420 } });
assert(layout.layout.source_panel_width === 400, "layout was not persisted");

console.log(JSON.stringify({
  status: "PASS",
  workspaceA: "created",
  workspaceB: "created",
  ingestion: "ready",
  groundedChat: "cited",
  report: "persisted-and-reopened",
  isolation: "denied",
  layout: "persisted",
}));
