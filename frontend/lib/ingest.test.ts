import assert from "node:assert/strict";
import test from "node:test";
import { buildLinkIngestRequest, isYouTubeUrl, normalizePublicUrl } from "./ingest.ts";

test("normalizePublicUrl adds https when the scheme is missing", () => {
  assert.equal(normalizePublicUrl("example.com/article"), "https://example.com/article");
  assert.equal(normalizePublicUrl("  https://example.com/a  "), "https://example.com/a");
  assert.equal(normalizePublicUrl(""), "");
});

test("isYouTubeUrl recognizes watch, short, and mobile hosts", () => {
  assert.equal(isYouTubeUrl("https://www.youtube.com/watch?v=dQw4w9WgXcQ"), true);
  assert.equal(isYouTubeUrl("youtu.be/dQw4w9WgXcQ"), true);
  assert.equal(isYouTubeUrl("m.youtube.com/watch?v=dQw4w9WgXcQ"), true);
  assert.equal(isYouTubeUrl("https://example.com/watch?v=dQw4w9WgXcQ"), false);
});

test("website ingest posts the normalized URL to the url endpoint", () => {
  const request = buildLinkIngestRequest({
    workspaceId: "ws-1",
    rawUrl: "docs.atlaslm.cloud/guide",
    language: "de",
  });
  assert.equal(request.path, "/api/v1/workspaces/ws-1/documents/url");
  assert.deepEqual(request.body, { url: "https://docs.atlaslm.cloud/guide" });
});

test("YouTube ingest posts URL and language to the youtube endpoint", () => {
  const request = buildLinkIngestRequest({
    workspaceId: "ws-1",
    rawUrl: "youtu.be/dQw4w9WgXcQ",
    language: "de",
  });
  assert.equal(request.path, "/api/v1/workspaces/ws-1/documents/youtube");
  assert.deepEqual(request.body, {
    url: "https://youtu.be/dQw4w9WgXcQ",
    language: "de",
  });
});

test("YouTube ingest defaults language to auto", () => {
  const request = buildLinkIngestRequest({
    workspaceId: "ws-1",
    rawUrl: "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
  });
  assert.equal(request.body.language, "auto");
});
