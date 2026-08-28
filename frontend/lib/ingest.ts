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
