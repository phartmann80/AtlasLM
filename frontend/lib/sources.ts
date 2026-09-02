// frontend/lib/sources.ts
export type SourceKind =
  | "pdf" | "docx" | "pptx" | "xlsx" | "image" | "audio" | "video" | "youtube" | "web";

export const SOURCE_TYPES = [
  { id: "pdf",   label: "PDF",         accept: ".pdf",            color: "#EF4444", status: "live", pipeline: "PyMuPDF page-by-page" },
  { id: "docx",  label: "Word",        accept: ".docx",           color: "#2563EB", status: "new",  pipeline: "Paragraphs + tables" },
  { id: "pptx",  label: "PowerPoint",  accept: ".pptx",           color: "#EA580C", status: "new",  pipeline: "Per-slide text + notes" },
  { id: "xlsx",  label: "Excel / CSV", accept: ".xlsx,.csv",      color: "#16A34A", status: "new",  pipeline: "Per-sheet rows" },
  { id: "image", label: "Image (OCR)", accept: ".png,.jpg,.jpeg,.webp,.heic,.heif", color: "#7c6bb5", status: "live", pipeline: "Tesseract OCR plus vision description" },
  { id: "audio", label: "Audio",       accept: ".mp3,.wav,.m4a,.aac,.ogg,.flac", color: "#3b6ea8", status: "live",  pipeline: "ffmpeg plus Gladia transcript" },
  { id: "video", label: "Video",       accept: ".mp4,.mov,.webm,.mkv", color: "#334155", status: "live", pipeline: "Audio strip plus Gladia transcript" },
  { id: "youtube", label: "YouTube",   accept: "url",             color: "#1e293b", status: "live",  pipeline: "Captions first, audio fallback" },
  { id: "web",   label: "Website",     accept: "url",             color: "#0EA5E9", status: "live", pipeline: "Readable text crawl" },
] as const;

import { apiClient } from "@/lib/apiClient";
import { buildLinkIngestRequest } from "@/lib/ingest";

export async function uploadSource(
  notebookId: string, file: File, _token?: string, language?: string,
) {
  const fd = new FormData();
  fd.append("file", file);
  if (language) fd.append("language", language);
  return apiClient.postForm(`/api/v1/workspaces/${notebookId}/documents`, fd);
}

export async function addUrlSource(
  notebookId: string, url: string, _token?: string, language?: string,
) {
  const request = buildLinkIngestRequest({
    workspaceId: notebookId,
    rawUrl: url,
    language,
  });
  return apiClient.post(request.path, request.body);
}

/** Format a chunk citation label: timestamp for audio/yt, else page/sheet. */
export function citationLabel(meta: {
  page?: number;
  sheet?: string;
  timestamp?: number;
  origin?: string;
  source_label?: string;
  external_url?: string;
  venue?: string;
}) {
  if (meta.origin === "deep_research") {
    if (meta.source_label === "Web" && meta.external_url) {
      try {
        return `Web · ${new URL(meta.external_url).hostname}`;
      } catch {
        return `Web`;
      }
    }
    return meta.venue || meta.source_label || "Deep Research";
  }
  if (meta.timestamp != null) {
    const s = Math.floor(meta.timestamp);
    const mm = String(Math.floor(s / 60)).padStart(2, "0");
    const ss = String(s % 60).padStart(2, "0");
    return `${mm}:${ss}`;
  }
  if (meta.sheet) return `Sheet ${meta.sheet}`;
  if (meta.page != null) return `p.${meta.page}`;
  return "";
}
