"use client";

import { useEffect, useRef, useState } from "react";
import { FileText, Loader2, SquareArrowOutUpRight, X } from "lucide-react";
import { apiUrl } from "@/lib/apiBase";
import { supabaseBrowser } from "@/lib/supabaseClient";

export type SourcePreviewChunk = {
  id: string;
  content: string;
  page_number?: number | null;
  timestamp?: number | null;
  sheet?: string | null;
  speaker?: string | null;
  start_ms?: number | null;
  end_ms?: number | null;
  region?: string | null;
  source_kind?: string | null;
  video_id?: string | null;
};

export type SourcePreviewData = {
  id: string;
  filename: string;
  file_type: string;
  source_url?: string | null;
  youtube_video_id?: string | null;
  channel_name?: string | null;
  thumbnail_path?: string | null;
  media_url?: string | null;
  has_media?: boolean;
  chunks: SourcePreviewChunk[];
};

function formatClock(msOrSec: number, fromMs = false) {
  const total = Math.max(0, Math.floor(fromMs ? msOrSec / 1000 : msOrSec));
  const m = Math.floor(total / 60);
  const s = (total % 60).toString().padStart(2, "0");
  return `${m}:${s}`;
}

async function mediaSrc(path: string): Promise<string> {
  const supabase = supabaseBrowser();
  const { data: { session } } = await supabase.auth.getSession();
  const token = session?.access_token;
  const res = await fetch(apiUrl(path), {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!res.ok) return "";
  const blob = await res.blob();
  return URL.createObjectURL(blob);
}

export default function SourcePreviewModal({
  filename,
  fileType,
  sourceUrl,
  preview,
  loading,
  seekMs,
  onClose,
}: {
  filename: string;
  fileType: string;
  sourceUrl?: string | null;
  preview: SourcePreviewData | null;
  loading: boolean;
  seekMs?: number | null;
  onClose: () => void;
}) {
  const kind = fileType.toLowerCase();
  const playerRef = useRef<HTMLVideoElement | HTMLAudioElement | null>(null);
  const [objectUrl, setObjectUrl] = useState("");

  useEffect(() => {
    let revoked = "";
    if (preview?.media_url && (kind.includes("image") || kind.includes("audio") || kind.includes("video"))) {
      void mediaSrc(preview.media_url).then((url) => {
        revoked = url;
        setObjectUrl(url);
      });
    }
    return () => {
      if (revoked) URL.revokeObjectURL(revoked);
    };
  }, [preview?.media_url, kind]);

  useEffect(() => {
    if (seekMs == null || !playerRef.current) return;
    playerRef.current.currentTime = seekMs / 1000;
  }, [seekMs, objectUrl]);

  const watchUrl = preview?.youtube_video_id
    ? `https://www.youtube.com/watch?v=${preview.youtube_video_id}`
    : sourceUrl;

  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={(event) => {
      if (event.target === event.currentTarget) onClose();
    }}>
      <div className="source-preview-modal media-source-preview" role="dialog" aria-modal="true">
        <div className="composer-heading">
          <div>
            <p className="eyebrow">Indexed source</p>
            <h2>{filename}</h2>
            <p>
              {kind.includes("image")
                ? "Image with extracted text Atlas can search and cite."
                : kind.includes("audio") || kind.includes("video") || kind.includes("youtube")
                  ? "Transcript with timestamps Atlas can search and cite."
                  : "Source text that Atlas can search and cite."}
            </p>
          </div>
          <button type="button" className="icon-button" onClick={onClose}><X size={17} /></button>
        </div>

        {watchUrl && (
          <a className="source-preview-link" href={watchUrl} target="_blank" rel="noreferrer">
            <SquareArrowOutUpRight size={14} /> Open original source
          </a>
        )}

        {kind.includes("image") && objectUrl && (
          <div className="media-split">
            <img src={objectUrl} alt={filename} className="media-image" />
            <div className="preview-chunks">
              {(preview?.chunks || []).map((chunk) => (
                <article className="preview-chunk" key={chunk.id}>
                  <span>{chunk.source_kind === "image_vision" ? "Visual description" : chunk.source_kind === "image_ocr" ? "Extracted text" : "Indexed excerpt"}</span>
                  <p>{chunk.content}</p>
                </article>
              ))}
            </div>
          </div>
        )}

        {(kind.includes("audio") || kind.includes("video")) && (
          <div className="media-player-block">
            {kind.includes("video") ? (
              <video ref={(el) => { playerRef.current = el; }} src={objectUrl} controls className="media-player" />
            ) : (
              <audio ref={(el) => { playerRef.current = el; }} src={objectUrl} controls className="media-player" />
            )}
          </div>
        )}

        {kind.includes("youtube") && preview?.youtube_video_id && (
          <div className="media-player-block">
            {preview.thumbnail_path && (
              <img src={preview.thumbnail_path} alt="" className="media-thumb" />
            )}
            <p className="media-channel">{preview.channel_name}</p>
          </div>
        )}

        {loading ? (
          <div className="preview-loading"><Loader2 size={22} className="spin" /><p>Loading the text Atlas indexed...</p></div>
        ) : preview?.chunks.length && !kind.includes("image") ? (
          <div className="preview-chunks">
            {preview.chunks.map((chunk) => (
              <article className="preview-chunk" key={chunk.id}>
                <button
                  type="button"
                  className="preview-seek"
                  onClick={() => {
                    if (chunk.video_id && kind.includes("youtube")) {
                      const start = chunk.start_ms != null
                        ? Math.floor(chunk.start_ms / 1000)
                        : Math.floor(chunk.timestamp || 0);
                      window.open(`https://www.youtube.com/watch?v=${chunk.video_id}&t=${start}`, "_blank");
                      return;
                    }
                    if (chunk.start_ms != null && playerRef.current) {
                      playerRef.current.currentTime = chunk.start_ms / 1000;
                      void playerRef.current.play();
                    }
                  }}
                >
                  {chunk.speaker ? `${chunk.speaker} · ` : ""}
                  {chunk.start_ms != null
                    ? formatClock(chunk.start_ms, true)
                    : chunk.timestamp != null
                      ? `Timestamp ${formatClock(chunk.timestamp)}`
                      : chunk.page_number
                        ? `Page ${chunk.page_number}`
                        : chunk.sheet
                          ? `Sheet ${chunk.sheet}`
                          : "Indexed excerpt"}
                </button>
                <p>{chunk.content}</p>
              </article>
            ))}
          </div>
        ) : !kind.includes("image") ? (
          <div className="preview-loading"><FileText size={22} /><p>No indexed text is available yet. Check the source status and try again.</p></div>
        ) : null}
      </div>
    </div>
  );
}
