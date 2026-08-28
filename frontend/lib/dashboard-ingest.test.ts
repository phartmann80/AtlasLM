import assert from "node:assert/strict";
import test from "node:test";
import {
  runDashboardLinkIngest,
  runDashboardSourceRetry,
  sourceRetryPath,
} from "./ingest.ts";

const WORKSPACE = "ws-atlas";

test("website input posts the url endpoint with { url } and never the text endpoint", async () => {
  const calls: Array<{ path: string; body: unknown; headers?: Record<string, string> }> = [];
  let reloaded = false;
  const result = await runDashboardLinkIngest({
    workspaceId: WORKSPACE,
    sourceInput: "docs.atlaslm.cloud/guide",
    language: "de",
    idempotencyKey: "idem-web",
    post: async (path, body, headers) => {
      calls.push({ path, body, headers });
      return { id: "doc-1" };
    },
    loadSources: async () => {
      reloaded = true;
    },
  });

  assert.equal(calls.length, 1);
  assert.equal(calls[0].path, `/api/v1/workspaces/${WORKSPACE}/documents/url`);
  assert.deepEqual(calls[0].body, { url: "https://docs.atlaslm.cloud/guide" });
  assert.equal(calls[0].headers?.["Idempotency-Key"], "idem-web");
  assert.equal(calls.some((call) => call.path.includes("/documents/text")), false);
  assert.equal(result.sourceInput, "");
  assert.equal(result.showSourceComposer, false);
  assert.equal(result.error, "");
  assert.equal(reloaded, true);
});

test("YouTube input posts url and language to the youtube endpoint", async () => {
  const calls: Array<{ path: string; body: unknown }> = [];
  const result = await runDashboardLinkIngest({
    workspaceId: WORKSPACE,
    sourceInput: "youtu.be/jNQXAC9IVRw",
    language: "de",
    idempotencyKey: "idem-yt",
    post: async (path, body) => {
      calls.push({ path, body });
      return { id: "doc-2" };
    },
    loadSources: async () => undefined,
  });

  assert.equal(calls.length, 1);
  assert.equal(calls[0].path, `/api/v1/workspaces/${WORKSPACE}/documents/youtube`);
  assert.deepEqual(calls[0].body, {
    url: "https://youtu.be/jNQXAC9IVRw",
    language: "de",
  });
  assert.equal(calls.some((call) => call.path.includes("/documents/text")), false);
  assert.equal(result.showSourceComposer, false);
});

test("link-mode failure preserves the entered URL, keeps the composer open, and shows an error", async () => {
  const result = await runDashboardLinkIngest({
    workspaceId: WORKSPACE,
    sourceInput: "https://www.youtube.com/watch?v=jNQXAC9IVRw",
    language: "de",
    idempotencyKey: "idem-fail",
    post: async () => {
      throw new Error("YouTube is private or captions are unavailable.");
    },
    loadSources: async () => {
      throw new Error("loadSources should not run after a failed post");
    },
  });

  assert.equal(result.sourceInput, "https://www.youtube.com/watch?v=jNQXAC9IVRw");
  assert.equal(result.showSourceComposer, true);
  assert.match(result.error, /YouTube is private/);
  assert.equal(result.posted.path, `/api/v1/workspaces/${WORKSPACE}/documents/youtube`);
});

test("source retry posts the same document retry endpoint and never deletes", async () => {
  const posts: string[] = [];
  const deletes: string[] = [];
  let reloaded = false;
  const result = await runDashboardSourceRetry({
    source: {
      id: "doc-failed",
      source_url: "https://example.com/notes",
      file_type: "url",
    },
    language: "auto",
    idempotencyKey: "retry-1",
    post: async (path) => {
      posts.push(path);
    },
    del: async (path) => {
      deletes.push(path);
    },
    loadSources: async () => {
      reloaded = true;
    },
  });

  assert.deepEqual(posts, [sourceRetryPath("doc-failed")]);
  assert.deepEqual(deletes, []);
  assert.equal(reloaded, true);
  assert.equal(result.error, "");
  assert.match(result.notice, /same source/);
});

test("file retry without a stored URL does not post or delete", async () => {
  const posts: string[] = [];
  const result = await runDashboardSourceRetry({
    source: { id: "doc-file", file_type: "pdf" },
    post: async (path) => {
      posts.push(path);
    },
    del: async () => {
      throw new Error("delete must not run");
    },
    loadSources: async () => {
      throw new Error("loadSources must not run");
    },
    idempotencyKey: "retry-file",
  });
  assert.deepEqual(posts, []);
  assert.match(result.error, /Re-add this file/);
});
