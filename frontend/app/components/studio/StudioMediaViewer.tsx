"use client";

import { useEffect, useRef, useState } from "react";
import { apiUrl } from "@/lib/apiBase";
import { supabaseBrowser } from "@/lib/supabaseClient";

type StudioMediaContent = {
  title?: string;
  transcript?: Array<{ speaker?: string; name?: string; text?: string; start?: number }>;
  slides?: Array<{ title?: string; bullets?: string[] }>;
  facts?: Array<{ label?: string; value?: string }>;
  headline?: string;
  sources?: Array<{ filename?: string; document_id?: string }>;
  audio_url?: string;
  video_url?: string;
  image_url?: string;
  download_url?: string;
  svg_url?: string;
  voices?: string[];
};

function formatClock(total: number) {
  const s = Math.max(0, Math.floor(total));
  return `${Math.floor(s / 60)}:${(s % 60).toString().padStart(2, "0")}`;
}

async function authedUrl(path: string): Promise<string> {
  const supabase = supabaseBrowser();
  const { data: { session } } = await supabase.auth.getSession();
  const res = await fetch(apiUrl(path), {
    headers: session?.access_token ? { Authorization: `Bearer ${session.access_token}` } : {},
  });
  if (!res.ok) return "";
  const blob = await res.blob();
  return URL.createObjectURL(blob);
}

export default function StudioMediaViewer({
  outputType,
  content,
}: {
  outputType: string;
  content: StudioMediaContent | Record<string, unknown>;
}) {
  const data = content as StudioMediaContent;
  const [src, setSrc] = useState("");
  const mediaRef = useRef<HTMLAudioElement | HTMLVideoElement | null>(null);
  const [pos, setPos] = useState(0);
  const [duration, setDuration] = useState(0);

  useEffect(() => {
    const path = data.audio_url || data.video_url || data.image_url;
    if (!path) return;
    let url = "";
    void authedUrl(path).then((value) => {
      url = value;
      setSrc(value);
    });
    return () => {
      if (url) URL.revokeObjectURL(url);
    };
  }, [data.audio_url, data.video_url, data.image_url]);

  const download = async (path?: string, name = "atlas-output") => {
    if (!path) return;
    const url = await authedUrl(path);
    if (!url) return;
    const a = document.createElement("a");
    a.href = url;
    a.download = name;
    a.click();
    URL.revokeObjectURL(url);
  };

  if (outputType === "audio_overview") {
    const lines = data.transcript || [];
    return (
      <div className="studio-media studio-audio">
        <div className="studio-wave">
          <audio
            ref={(el) => { mediaRef.current = el; }}
            src={src}
            onTimeUpdate={(event) => setPos(event.currentTarget.currentTime)}
            onLoadedMetadata={(event) => setDuration(event.currentTarget.duration || 0)}
            controls
          />
          <div className="studio-progress" aria-hidden>
            <span style={{ width: `${duration ? Math.min(100, (pos / duration) * 100) : 0}%` }} />
          </div>
          <div className="studio-times">{formatClock(pos)} / {formatClock(duration)}</div>
        </div>
        <button type="button" className="primary-button" onClick={() => void download(data.download_url, "audio-overview.mp3")}>Download MP3</button>
        <div className="studio-script">
          {lines.map((line, index) => (
            <p key={index}><strong>{line.name || (line.speaker === "B" ? "Theo" : "Maya")}:</strong> {line.text}</p>
          ))}
        </div>
        <SourcesList sources={data.sources} />
      </div>
    );
  }

  if (outputType === "video_overview") {
    return (
      <div className="studio-media studio-video">
        <video
          ref={(el) => { mediaRef.current = el; }}
          src={src}
          controls
          className="studio-video-player"
        />
        <button type="button" className="primary-button" onClick={() => void download(data.download_url, "video-overview.mp4")}>Download MP4</button>
        <ol className="studio-slide-list">
          {(data.slides || []).map((slide, index) => (
            <li key={index}>
              <strong>{slide.title}</strong>
              <ul>{(slide.bullets || []).map((bullet, bulletIndex) => <li key={bulletIndex}>{bullet}</li>)}</ul>
            </li>
          ))}
        </ol>
        <SourcesList sources={data.sources} />
      </div>
    );
  }

  if (outputType === "infographic") {
    return (
      <div className="studio-media studio-infographic">
        {src && <img src={src} alt={data.headline || "Infographic"} className="studio-infographic-image" />}
        <div className="studio-actions">
          <button type="button" className="primary-button" onClick={() => void download(data.download_url, "infographic.png")}>Download PNG</button>
          <button type="button" className="secondary-button" onClick={() => void download(data.svg_url, "infographic.svg")}>Download SVG</button>
        </div>
        <SourcesList sources={data.sources} />
      </div>
    );
  }

  return null;
}

function SourcesList({ sources }: { sources?: Array<{ filename?: string }> }) {
  if (!sources?.length) return null;
  return (
    <div className="studio-sources-used">
      <h3>Sources used</h3>
      <ul>
        {sources.map((source, index) => (
          <li key={index}>{source.filename || `Source ${index + 1}`}</li>
        ))}
      </ul>
    </div>
  );
}
