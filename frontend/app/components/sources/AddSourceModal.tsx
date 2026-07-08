"use client";

import React, { useState, useRef } from "react";
import { apiClient } from "@/lib/apiClient";

export default function AddSourceModal({
  notebookId,
  token,
  onClose,
  onAdded,
}: {
  notebookId: string;
  token: string;
  onClose: () => void;
  onAdded?: (result: any) => void;
}) {
  const [active, setActive] = useState<"link" | "website" | "youtube" | "paste" | null>(null);
  const [url, setUrl] = useState("");
  const [pasteTitle, setPasteTitle] = useState("");
  const [pasteContent, setPasteContent] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");

  const [acceptTypes, setAcceptTypes] = useState("");
  const fileInputRef = useRef<HTMLInputElement>(null);

  function cleanErrorMessage(error: any): string {
    const msg = error?.message || "";
    if (msg.includes(" -> ") || msg.includes("→") || msg.includes(" : ") || msg.includes("status:")) {
      try {
        const jsonMatch = msg.match(/(\{.*\})/);
        if (jsonMatch) {
          const parsed = JSON.parse(jsonMatch[1]);
          if (parsed.detail) {
            if (typeof parsed.detail === "string") return parsed.detail;
            if (Array.isArray(parsed.detail)) {
              return parsed.detail.map((d: any) => d.msg || JSON.stringify(d)).join(", ");
            }
          }
        }
      } catch (e) {
        // ignore
      }
    }
    return msg || "AtlasLM could not ingest this source.";
  }

  function normalizeUrlInput(value: string): string {
    const trimmed = value.trim();
    if (!trimmed) return "";
    if (/^[a-z][a-z0-9+.-]*:\/\//i.test(trimmed)) return trimmed;
    return `https://${trimmed}`;
  }

  function isYouTubeUrl(value: string): boolean {
    return /(^|\.)youtube\.com|(^|\.)youtu\.be/i.test(value);
  }

  function handleFileClick(type: "pdf" | "docx" | "xlsx" | "pptx") {
    if (type === "pdf") {
      setAcceptTypes(".pdf");
    } else if (type === "docx") {
      setAcceptTypes(".docx,.txt,.md");
    } else if (type === "xlsx") {
      setAcceptTypes(".xlsx,.csv");
    } else if (type === "pptx") {
      setAcceptTypes(".pptx");
    }
    setErr(null);
    setTimeout(() => {
      fileInputRef.current?.click();
    }, 50);
  }

  async function handleFileSelected(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setBusy(true);
    setErr(null);
    try {
      const fd = new FormData();
      fd.append("file", file);
      const res = await apiClient.postForm<any>(`/api/v1/workspaces/${notebookId}/documents`, fd);
      onAdded?.(res);
      onClose();
    } catch (error: any) {
      setErr(cleanErrorMessage(error));
    } finally {
      setBusy(false);
    }
  }

  async function handleWebsiteSubmit() {
    if (!url.trim()) return;
    setBusy(true);
    setErr(null);
    try {
      const res = await apiClient.post<any>(`/api/v1/workspaces/${notebookId}/documents/url`, { url: normalizeUrlInput(url) });
      onAdded?.(res);
      onClose();
    } catch (error: any) {
      setErr(cleanErrorMessage(error));
    } finally {
      setBusy(false);
    }
  }

  async function handleYoutubeSubmit() {
    if (!url.trim()) return;
    setBusy(true);
    setErr(null);
    try {
      const res = await apiClient.post<any>(`/api/v1/workspaces/${notebookId}/documents/youtube`, { url: normalizeUrlInput(url) });
      onAdded?.(res);
      onClose();
    } catch (error: any) {
      setErr(cleanErrorMessage(error));
    } finally {
      setBusy(false);
    }
  }

  async function ingestLinkValue(rawUrl: string) {
    if (!rawUrl.trim()) return;
    setBusy(true);
    setErr(null);
    const normalized = normalizeUrlInput(rawUrl);
    try {
      const path = isYouTubeUrl(normalized)
        ? `/api/v1/workspaces/${notebookId}/documents/youtube`
        : `/api/v1/workspaces/${notebookId}/documents/url`;
      const res = await apiClient.post<any>(path, { url: normalized });
      onAdded?.(res);
      onClose();
    } catch (error: any) {
      setErr(cleanErrorMessage(error));
    } finally {
      setBusy(false);
    }
  }

  async function handleLinkSubmit() {
    await ingestLinkValue(url);
  }

  async function handlePasteSubmit() {
    if (!pasteContent.trim()) return;
    setBusy(true);
    setErr(null);
    try {
      const res = await apiClient.post<any>(`/api/v1/workspaces/${notebookId}/documents/text`, {
        title: pasteTitle.trim() || "Pasted Document",
        content: pasteContent.trim(),
      });
      onAdded?.(res);
      onClose();
    } catch (error: any) {
      setErr(cleanErrorMessage(error));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div
      className="modal-backdrop"
      style={{ display: "flex" }}
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-inner">
          <button className="modal-close" onClick={onClose} title="Close">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round">
              <path d="M18 6L6 18M6 6l12 12" />
            </svg>
          </button>

          <input
            type="file"
            ref={fileInputRef}
            accept={acceptTypes}
            onChange={handleFileSelected}
            style={{ display: "none" }}
          />

          {active === null ? (
            <>
              <h2>Add a source to AtlasLM</h2>
              <p className="sub">Sources let AtlasLM ground every answer in your own material.</p>

              <div className="web-find">
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="#4ade80" strokeWidth="2" strokeLinecap="round">
                  <circle cx="11" cy="11" r="7" />
                  <path d="M21 21l-4.3-4.3" />
                </svg>
                <input
                  type="text"
                  placeholder="Paste any link to ingest"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") {
                      e.preventDefault();
                      ingestLinkValue(searchQuery);
                    }
                  }}
                  disabled={busy}
                />
                <button
                  className="go"
                  disabled={busy || !searchQuery.trim()}
                  onClick={() => ingestLinkValue(searchQuery)}
                >
                  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M22 2L11 13M22 2l-7 20-4-9-9-4z" />
                  </svg>
                </button>
              </div>
              {err && <div className="mt-2 text-xs text-orange-500 font-medium">{err}</div>}

              <div className="or-div">Or upload your files</div>

              <div className="flex flex-col gap-1 max-h-[50vh] overflow-y-auto pr-1">
                <button className="src-row" onClick={() => handleFileClick("pdf")}>
                  <div className="src-ic">
                    <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="#f87171" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                      <path d="M14 2v6h6" />
                    </svg>
                  </div>
                  <div>
                    <div className="sr-name">PDF</div>
                    <div className="sr-desc">Reports, papers, books</div>
                  </div>
                </button>

                <button className="src-row" onClick={() => handleFileClick("docx")}>
                  <div className="src-ic">
                    <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="#60a5fa" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                      <path d="M14 2v6h6M8 13h8M8 17h8" />
                    </svg>
                  </div>
                  <div>
                    <div className="sr-name">Document</div>
                    <div className="sr-desc">DOCX, TXT, Markdown</div>
                  </div>
                </button>

                <button className="src-row" onClick={() => handleFileClick("xlsx")}>
                  <div className="src-ic">
                    <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="#4ade80" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <rect x="3" y="3" width="18" height="18" rx="2" />
                      <path d="M3 9h18M9 3v18" />
                    </svg>
                  </div>
                  <div>
                    <div className="sr-name">Spreadsheet</div>
                    <div className="sr-desc">XLSX, CSV</div>
                  </div>
                </button>

                <button className="src-row" onClick={() => handleFileClick("pptx")}>
                  <div className="src-ic">
                    <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="#fbbf24" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <rect x="2" y="4" width="20" height="14" rx="2" />
                      <path d="M8 21h8M12 18v3" />
                    </svg>
                  </div>
                  <div>
                    <div className="sr-name">Slides</div>
                    <div className="sr-desc">PPTX presentations</div>
                  </div>
                </button>

                <button className="src-row" onClick={() => { setActive("link"); setErr(null); setUrl(""); }}>
                  <div className="src-ic">
                    <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="#22d3ee" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M10 13a5 5 0 0 0 7.1 0l2-2a5 5 0 0 0-7.1-7.1l-1.1 1.1" />
                      <path d="M14 11a5 5 0 0 0-7.1 0l-2 2a5 5 0 0 0 7.1 7.1l1.1-1.1" />
                    </svg>
                  </div>
                  <div>
                    <div className="sr-name">Link or video</div>
                    <div className="sr-desc">Web pages and YouTube transcripts</div>
                  </div>
                </button>

                <button className="src-row" onClick={() => { setActive("website"); setErr(null); setUrl(""); }}>
                  <div className="src-ic">
                    <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="#60a5fa" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <circle cx="12" cy="12" r="9" />
                      <path d="M3 12h18M12 3a15 15 0 0 1 0 18M12 3a15 15 0 0 0 0 18" />
                    </svg>
                  </div>
                  <div>
                    <div className="sr-name">Website</div>
                    <div className="sr-desc">Paste any page URL</div>
                  </div>
                </button>

                <button className="src-row" onClick={() => { setActive("youtube"); setErr(null); setUrl(""); }}>
                  <div className="src-ic">
                    <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="#f87171" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <rect x="2" y="5" width="20" height="14" rx="4" />
                      <path d="M10 9.5v5l4.5-2.5z" fill="#f87171" stroke="none" />
                    </svg>
                  </div>
                  <div>
                    <div className="sr-name">YouTube</div>
                    <div className="sr-desc">Transcribe any video link</div>
                  </div>
                </button>

                <button className="src-row" onClick={() => { setActive("paste"); setErr(null); setPasteTitle(""); setPasteContent(""); }}>
                  <div className="src-ic">
                    <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="#a78bfa" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <rect x="8" y="2" width="8" height="4" rx="1" />
                      <path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2M9 12h6M9 16h6" />
                    </svg>
                  </div>
                  <div>
                    <div className="sr-name">Copied text</div>
                    <div className="sr-desc">Paste notes or any text</div>
                  </div>
                </button>

                <div className="src-row soon">
                  <div className="src-ic">
                    <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="#34d399" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3z" />
                      <path d="M19 10v2a7 7 0 0 1-14 0v-2M12 19v3" />
                    </svg>
                  </div>
                  <div>
                    <div className="sr-name">Audio</div>
                    <div className="sr-desc">MP3, WAV transcription</div>
                  </div>
                  <span className="soon-badge">SOON</span>
                </div>

                <div className="src-row soon">
                  <div className="src-ic">
                    <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="#fb923c" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <rect x="3" y="3" width="18" height="18" rx="2" />
                      <circle cx="8.5" cy="8.5" r="1.5" />
                      <path d="M21 15l-5-5L5 21" />
                    </svg>
                  </div>
                  <div>
                    <div className="sr-name">Image</div>
                    <div className="sr-desc">PNG, JPG with OCR</div>
                  </div>
                  <span className="soon-badge">SOON</span>
                </div>
              </div>
            </>
          ) : (
            <div className="flex flex-col">
              <button
                className="text-orange-500 hover:text-orange-400 text-xs font-bold mb-4 flex items-center gap-1 cursor-pointer self-start"
                onClick={() => { setActive(null); setErr(null); }}
              >
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M19 12H5M12 19l-7-7 7-7" />
                </svg>
                <span>Back to sources list</span>
              </button>

              {active === "link" && (
                <>
                  <h2>Ingest Link or Video</h2>
                  <p className="sub">Paste a public URL. AtlasLM currently ingests web pages and YouTube transcripts through the live backend.</p>
                  <div className="mt-4 flex flex-col gap-3">
                    <input
                      type="text"
                      value={url}
                      onChange={(e) => setUrl(e.target.value)}
                      placeholder="example.com/article or youtube.com/watch?v=..."
                      className="w-full bg-zinc-900 border border-zinc-800 rounded-lg p-3 text-sm text-zinc-200 focus:outline-none focus:border-zinc-700 transition-colors"
                      disabled={busy}
                    />
                    <button
                      disabled={busy || !url.trim()}
                      onClick={handleLinkSubmit}
                      className="w-full bg-orange-600 hover:bg-orange-500 disabled:opacity-50 text-white font-bold py-3 rounded-lg text-xs tracking-wider uppercase transition-colors"
                    >
                      {busy ? "Ingesting..." : "Ingest link"}
                    </button>
                  </div>
                  <p className="mt-3 text-[11px] leading-5 text-zinc-500">
                    Instagram, TikTok, LinkedIn, and other social video transcription still need the generic media transcription backend.
                  </p>
                </>
              )}

              {active === "website" && (
                <>
                  <h2>Ingest Website</h2>
                  <p className="sub">Paste a website page URL to parse its content. Bare domains are accepted.</p>
                  <div className="mt-4 flex flex-col gap-3">
                    <input
                      type="text"
                      value={url}
                      onChange={(e) => setUrl(e.target.value)}
                      placeholder="example.com/article"
                      className="w-full bg-zinc-900 border border-zinc-800 rounded-lg p-3 text-sm text-zinc-200 focus:outline-none focus:border-zinc-700 transition-colors"
                      disabled={busy}
                    />
                    <button
                      disabled={busy || !url.trim()}
                      onClick={handleWebsiteSubmit}
                      className="w-full bg-orange-600 hover:bg-orange-500 disabled:opacity-50 text-white font-bold py-3 rounded-lg text-xs tracking-wider uppercase transition-colors"
                    >
                      {busy ? "Ingesting..." : "Ingest Web Page"}
                    </button>
                  </div>
                </>
              )}

              {active === "youtube" && (
                <>
                  <h2>Ingest YouTube</h2>
                  <p className="sub">Paste a YouTube link. AtlasLM will transcribe the video captions.</p>
                  <div className="mt-4 flex flex-col gap-3">
                    <input
                      type="text"
                      value={url}
                      onChange={(e) => setUrl(e.target.value)}
                      placeholder="Paste a YouTube link"
                      className="w-full bg-zinc-900 border border-zinc-800 rounded-lg p-3 text-sm text-zinc-200 focus:outline-none focus:border-zinc-700 transition-colors"
                      disabled={busy}
                    />
                    <button
                      disabled={busy || !url.trim()}
                      onClick={handleYoutubeSubmit}
                      className="w-full bg-orange-600 hover:bg-orange-500 disabled:opacity-50 text-white font-bold py-3 rounded-lg text-xs tracking-wider uppercase transition-colors"
                    >
                      {busy ? "Transcribing..." : "Transcribe video"}
                    </button>
                  </div>
                </>
              )}

              {active === "paste" && (
                <>
                  <h2>Ingest Pasted Text</h2>
                  <p className="sub">Provide a title and paste your research notes or text.</p>
                  <div className="mt-4 flex flex-col gap-3">
                    <input
                      type="text"
                      value={pasteTitle}
                      onChange={(e) => setPasteTitle(e.target.value)}
                      placeholder="Document title"
                      className="w-full bg-zinc-900 border border-zinc-800 rounded-lg p-3 text-sm text-zinc-200 focus:outline-none focus:border-zinc-700 transition-colors"
                      disabled={busy}
                    />
                    <textarea
                      value={pasteContent}
                      onChange={(e) => setPasteContent(e.target.value)}
                      placeholder="Paste text contents here"
                      rows={6}
                      className="w-full bg-zinc-900 border border-zinc-800 rounded-lg p-3 text-sm text-zinc-200 focus:outline-none focus:border-zinc-700 transition-colors"
                      disabled={busy}
                    />
                    <button
                      disabled={busy || !pasteContent.trim()}
                      onClick={handlePasteSubmit}
                      className="w-full bg-orange-600 hover:bg-orange-500 disabled:opacity-50 text-white font-bold py-3 rounded-lg text-xs tracking-wider uppercase transition-colors"
                    >
                      {busy ? "Ingesting..." : "Ingest text"}
                    </button>
                  </div>
                </>
              )}

              {err && <div className="mt-3 text-xs text-red-400 font-medium">{err}</div>}
              {busy && (
                <div className="mt-3 text-[11px] text-zinc-400 flex items-center gap-2">
                  <svg className="w-3.5 h-3.5 animate-spin text-orange-500" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                  </svg>
                  <span>AtlasLM pipeline ingesting source...</span>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
