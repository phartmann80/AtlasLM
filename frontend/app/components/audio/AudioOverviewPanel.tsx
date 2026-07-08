// frontend/app/components/audio/AudioOverviewPanel.tsx
// Patch 010 - Studio Finish. Audio Overview generation + player + export +
// public share. Mounts inside the dashboard Studio column. Production port of
// the approved preview. House style: ASCII punctuation only (passes T10).
"use client";

import { useEffect, useRef, useState } from "react";
import {
  generateAudio, createShareLink, exportUrl,
  type AudioOverview, type ScriptLine,
} from "@/lib/audio";
import "./audio-overview.css";

type Props = {
  workspaceId: string;
  token: string;
  docIds?: string[];
};

const VOICES = [
  { id: "atlas-offline", label: "Atlas Voice", sub: "On-device when voice models are installed", badge: "default", enabled: true },
  { id: "studio-cloud", label: "Studio HD", sub: "Cloud narration engine is not connected yet", badge: "soon", enabled: false },
];
const STYLES = [
  { id: "deep_dive", label: "Deep Dive", sub: "Two hosts, conversational" },
  { id: "brief", label: "Brief", sub: "One host, 60-second summary" },
];

function fmt(s: number) {
  const m = Math.floor(s / 60);
  const r = Math.floor(s % 60);
  return `${m}:${r.toString().padStart(2, "0")}`;
}

export default function AudioOverviewPanel({ workspaceId, token, docIds }: Props) {
  const [phase, setPhase] = useState<"setup" | "generating" | "ready">("setup");
  const [voice, setVoice] = useState("atlas-offline");
  const [style, setStyle] = useState("deep_dive");
  const [overview, setOverview] = useState<AudioOverview | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [shareUrl, setShareUrl] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  const audioRef = useRef<HTMLAudioElement | null>(null);
  const [playing, setPlaying] = useState(false);
  const [pos, setPos] = useState(0);
  const copyTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => () => { if (copyTimer.current) clearTimeout(copyTimer.current); }, []);

  const hasSources = Boolean(docIds?.length);

  async function onGenerate() {
    if (!hasSources) {
      setError("Add at least one ready source before generating an audio overview.");
      return;
    }
    setError(null);
    setPhase("generating");
    try {
      const ov = await generateAudio(workspaceId, token, {
        title: "Audio Overview", style, voice, doc_ids: docIds,
      });
      setOverview(ov);
      setPhase("ready");
    } catch (e: any) {
      setError(e?.message ?? "Something went wrong. Try again.");
      setPhase("setup");
    }
  }

  function reset() {
    setPhase("setup"); setOverview(null); setShareUrl(null);
    setPlaying(false); setPos(0); setError(null);
  }

  function togglePlay() {
    const el = audioRef.current;
    if (!el) return;
    if (el.paused) { el.play(); setPlaying(true); }
    else { el.pause(); setPlaying(false); }
  }

  async function onShare() {
    if (!overview) return;
    try {
      const r = await createShareLink(workspaceId, overview.overview_id, token);
      setShareUrl(`${window.location.origin}${r.share_url}`);
    } catch (e: any) {
      setError(e?.message ?? "Could not create the public link.");
    }
  }

  function copyLink() {
    if (!shareUrl) return;
    navigator.clipboard?.writeText(shareUrl);
    setCopied(true);
    if (copyTimer.current) clearTimeout(copyTimer.current);
    copyTimer.current = setTimeout(() => setCopied(false), 1600);
  }

  const lines: ScriptLine[] = overview?.transcript ?? [];
  const dur = overview?.duration ?? 0;
  const activeLine = lines.reduce(
    (acc, l, i) => (pos >= (l.start ?? 0) ? i : acc), 0);

  return (
    <div className="ao-root">
      {phase !== "ready" ? (
        <div className="ao-setup">
          <div className="ao-hero">
            <div className="ao-hero-icon" aria-hidden>🎧</div>
            <h3>Audio Overview</h3>
          <p>Two hosts turn your ready sources into a short, listenable conversation grounded in the selected notebook material.</p>
          </div>

          <div className="ao-field">
            <span className="ao-label">Voice</span>
            {VOICES.map((v) => (
              <button key={v.id} type="button"
                className={`ao-opt ${voice === v.id ? "is-sel" : ""}`}
                disabled={phase === "generating" || !v.enabled} onClick={() => setVoice(v.id)}>
                <span className="ao-opt-main">
                  {v.label}
                  <span className={`ao-tag ao-tag-${v.badge}`}>{v.badge}</span>
                </span>
                <span className="ao-opt-sub">{v.sub}</span>
              </button>
            ))}
          </div>

          <div className="ao-field">
            <span className="ao-label">Format</span>
            <div className="ao-grid2">
              {STYLES.map((s) => (
                <button key={s.id} type="button"
                  className={`ao-opt ${style === s.id ? "is-sel" : ""}`}
                  disabled={phase === "generating"} onClick={() => setStyle(s.id)}>
                  <span className="ao-opt-main">{s.label}</span>
                  <span className="ao-opt-sub">{s.sub}</span>
                </button>
              ))}
            </div>
          </div>

          {error && <p className="ao-error">{error}</p>}

          <button type="button" className="ao-generate"
            disabled={phase === "generating" || !hasSources} onClick={onGenerate}>
            {phase === "generating" ? "Generating..." : "Generate Audio Overview"}
          </button>
          <p className="ao-note">
            {hasSources
              ? "Atlas Voice runs on-device when voice models are available; otherwise the backend returns a timed transcript track."
              : "Audio generation unlocks after a source finishes indexing."}
          </p>
        </div>
      ) : (
        <div className="ao-player-wrap">
          <div className="ao-topbar">
            <span>Audio Overview</span>
            <button type="button" className="ao-new" onClick={reset}>New</button>
          </div>

          <div className="ao-player">
            <div className="ao-now">
              <div className="ao-now-icon" aria-hidden>🎧</div>
              <div className="ao-now-meta">
                <div className="ao-now-title">{overview?.title}</div>
                <div className="ao-now-sub">{fmt(dur)} · {overview?.voice}</div>
              </div>
            </div>

            {overview?.audio_url && (
              <audio ref={audioRef} src={overview.audio_url}
                onTimeUpdate={(e) => setPos(e.currentTarget.currentTime)}
                onEnded={() => setPlaying(false)} preload="metadata" />
            )}

            <div className="ao-progress">
              <div className="ao-progress-fill"
                style={{ width: `${dur ? (pos / dur) * 100 : 0}%` }} />
            </div>
            <div className="ao-times"><span>{fmt(pos)}</span><span>{fmt(dur)}</span></div>

            <div className="ao-controls">
              <button type="button" className="ao-play" onClick={togglePlay}
                aria-label={playing ? "Pause" : "Play"}>
                {playing ? "Pause" : "Play"}
              </button>
            </div>
          </div>

          <div className="ao-transcript">
            <span className="ao-label">Transcript</span>
            {lines.map((l, i) => (
              <div key={i} className={`ao-line ${i === activeLine && playing ? "is-active" : ""}`}>
                <span className={`ao-spk ao-spk-${l.speaker}`}>{l.name}</span>
                <p>{l.text}{l.cite ? <span className="ao-cite">[{l.cite}]</span> : null}</p>
              </div>
            ))}
          </div>

          <div className="ao-actions">
            <span className="ao-label">Export</span>
            <div className="ao-grid2">
              <a className="ao-export" href={exportUrl(workspaceId, overview!.overview_id, "pdf")}>PDF</a>
              <a className="ao-export" href={exportUrl(workspaceId, overview!.overview_id, "md")}>Markdown</a>
            </div>

            <span className="ao-label">Share</span>
            {!shareUrl ? (
              <button type="button" className="ao-share" onClick={onShare}>
                Create public link
              </button>
            ) : (
              <div className="ao-link">
                <input readOnly value={shareUrl} aria-label="Public link" />
                <button type="button" onClick={copyLink} className={copied ? "is-copied" : ""}>
                  {copied ? "Copied" : "Copy"}
                </button>
              </div>
            )}
            <p className="ao-note">Listeners get a clean player and a "Made with AtlasLM" credit. They never see your sources.</p>
          </div>
          {error && <p className="ao-error">{error}</p>}
        </div>
      )}
    </div>
  );
}
