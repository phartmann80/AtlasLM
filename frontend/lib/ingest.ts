/**
 * Shared website / YouTube ingest helpers for the dashboard.
 * Keep URL normalization and route selection here so the composer cannot
 * send a bare host to the YouTube endpoint or drop the transcription language.
 */

export const TRANSCRIPTION_LANGUAGES = [
  { value: "auto", label: "Auto detect" },
  { value: "en", label: "English" },
  { value: "de", label: "German" },
  { value: "es", label: "Spanish" },
  { value: "fr", label: "French" },
  { value: "pt", label: "Portuguese" },
  { value: "it", label: "Italian" },
  { value: "nl", label: "Dutch" },
  { value: "ar", label: "Arabic" },
  { value: "hi", label: "Hindi" },
  { value: "ja", label: "Japanese" },
  { value: "ko", label: "Korean" },
  { value: "zh", label: "Chinese" },
] as const;

export type LinkIngestRequest = {
  path: string;
  body: { url: string; language?: string };
};

export function normalizePublicUrl(value: string): string {
  const trimmed = value.trim();
  if (!trimmed) return "";
  if (/^[a-z][a-z0-9+.-]*:\/\//i.test(trimmed)) return trimmed;
  return `https://${trimmed}`;
}

export function isYouTubeUrl(value: string): boolean {
  const candidate = normalizePublicUrl(value);
  if (!candidate) return false;
  try {
    const host = new URL(candidate).hostname.replace(/^www\./i, "").toLowerCase();
    return (
      host === "youtube.com"
      || host.endsWith(".youtube.com")
      || host === "youtu.be"
      || host === "m.youtube.com"
      || host === "music.youtube.com"
    );
  } catch {
    return /(?:^|\.)youtube\.com|(?:^|\.)youtu\.be/i.test(candidate);
  }
}

export function buildLinkIngestRequest(opts: {
  workspaceId: string;
  rawUrl: string;
  language?: string;
}): LinkIngestRequest {
  const url = normalizePublicUrl(opts.rawUrl);
  if (!url) {
    throw new Error("Enter a website or YouTube URL.");
  }
  if (isYouTubeUrl(url)) {
    return {
      path: `/api/v1/workspaces/${opts.workspaceId}/documents/youtube`,
      body: {
        url,
        language: opts.language?.trim() || "auto",
      },
    };
  }
  return {
    path: `/api/v1/workspaces/${opts.workspaceId}/documents/url`,
    body: { url },
  };
}

export type JsonPost = (
  path: string,
  body: unknown,
  headers?: Record<string, string>,
) => Promise<unknown>;

export type DashboardLinkIngestResult = {
  sourceInput: string;
  showSourceComposer: boolean;
  error: string;
  notice: string;
  posted: { path: string; body: { url: string; language?: string } };
};

/**
 * Production dashboard Paste-a-link submit path.
 * Always posts `request.path` / `request.body` from buildLinkIngestRequest.
 * Success clears the URL, reloads sources, and closes the composer.
 * Failure keeps the entered URL, keeps the composer open, and returns the error.
 */
export async function runDashboardLinkIngest(opts: {
  workspaceId: string;
  sourceInput: string;
  language?: string;
  post: JsonPost;
  loadSources: (workspaceId: string) => Promise<void>;
  idempotencyKey: string;
}): Promise<DashboardLinkIngestResult> {
  const request = buildLinkIngestRequest({
    workspaceId: opts.workspaceId,
    rawUrl: opts.sourceInput,
    language: opts.language,
  });
  try {
    await opts.post(request.path, request.body, {
      "Idempotency-Key": opts.idempotencyKey,
    });
    await opts.loadSources(opts.workspaceId);
    return {
      sourceInput: "",
      showSourceComposer: false,
      error: "",
      notice: "Source added. Atlas is preparing it for grounded answers.",
      posted: request,
    };
  } catch (caught) {
    const message = caught instanceof Error && caught.message
      ? caught.message
      : "Atlas could not reach that link.";
    return {
      sourceInput: opts.sourceInput,
      showSourceComposer: true,
      error: message,
      notice: "",
      posted: request,
    };
  }
}

export function sourceRetryPath(documentId: string): string {
  return `/api/v1/documents/${documentId}/retry`;
}

export async function runDashboardSourceRetry(opts: {
  source: { id: string; source_url?: string | null; file_type?: string };
  language?: string;
  post: JsonPost;
  del?: (path: string) => Promise<void>;
  loadSources: () => Promise<void>;
  idempotencyKey: string;
}): Promise<{ error: string; notice: string }> {
  const kind = (opts.source.file_type || "").toLowerCase();
  const isLink = Boolean(opts.source.source_url) || kind.includes("url") || kind.includes("youtube") || kind.includes("web");
  if (!isLink) {
    return {
      error: "Re-add this file to retry. AtlasLM does not keep the original upload for retry.",
      notice: "",
    };
  }
  await opts.post(
    sourceRetryPath(opts.source.id),
    { language: opts.language?.trim() || "auto" },
    { "Idempotency-Key": opts.idempotencyKey },
  );
  await opts.loadSources();
  return {
    error: "",
    notice: "Retry queued. Atlas is indexing the same source again.",
  };
}
