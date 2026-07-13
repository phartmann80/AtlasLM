"use client";

import Link from "next/link";
import {
  ArrowUpRight,
  BookOpen,
  BrainCircuit,
  Check,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  CircleAlert,
  Cloud,
  FileAudio,
  FileText,
  FileUp,
  FolderOpen,
  Globe2,
  Headphones,
  Layers3,
  Lightbulb,
  Loader2,
  MessageCircle,
  Mic2,
  MoreHorizontal,
  Network,
  PanelRight,
  Play,
  Plus,
  Quote,
  Search,
  Send,
  Sparkles,
  SquareArrowOutUpRight,
  Trash2,
  UploadCloud,
  Video,
  WandSparkles,
  X,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import type { CSSProperties, FormEvent } from "react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { apiClient } from "@/lib/apiClient";
import { type AudioOverview } from "@/lib/audio";
import "./atlas-workspace.css";

type Workspace = { id: string; name: string; created_at?: string };
type SourceStatus = "pending" | "processing" | "ready" | "failed";
type Source = {
  id: string;
  workspace_id?: string;
  filename: string;
  file_type: string;
  source_url?: string | null;
  status: SourceStatus;
  error_message?: string | null;
  created_at: string;
};
type Citation = {
  chunk_id?: string;
  document_id?: string;
  filename?: string;
  content?: string;
  text?: string;
  page_number?: number;
  timestamp?: number;
  source_url?: string;
  external_url?: string;
  quote?: string;
  source_label?: string;
  venue?: string;
  file_type?: string;
};
type Message = {
  id: string;
  role: "user" | "assistant";
  content: string;
  citations?: Citation[];
};
type SourcePreview = {
  id: string;
  filename: string;
  file_type: string;
  source_url?: string | null;
  status: SourceStatus;
  error_message?: string | null;
  chunks: Array<{
    id: string;
    content: string;
    page_number?: number | null;
    timestamp?: number | null;
    sheet?: string | null;
  }>;
};
type StudioOutput = {
  id: string;
  output_type: "report" | "mind_map" | "study_guide" | "quiz" | "flashcards";
  title: string;
  status: string;
  content: Record<string, unknown> | string | null;
  error?: string | null;
  created_at: string;
  citations?: Citation[];
};
type Panel = "workspace" | "sources" | "outputs" | "audio";
type SourceFilter = "all" | "ready" | "processing";
type AnswerMode = "auto" | "sources" | "general";
type LayoutState = {
  source_panel_width: number;
  output_panel_width: number;
  source_panel_collapsed: boolean;
  output_panel_collapsed: boolean;
};

const DEFAULT_LAYOUT: LayoutState = {
  source_panel_width: 320,
  output_panel_width: 360,
  source_panel_collapsed: false,
  output_panel_collapsed: false,
};

const SOURCE_TYPES = [
  { label: "PDFs", detail: "Research papers, chapters, reports", icon: FileText, tone: "coral" },
  { label: "Websites", detail: "Articles, docs, public pages", icon: Globe2, tone: "blue" },
  { label: "YouTube", detail: "Video transcripts with timestamps", icon: Video, tone: "red" },
  { label: "Audio files", detail: "Lectures, interviews, recordings", icon: FileAudio, tone: "violet" },
  { label: "Google Docs", detail: "Bring in connected documents", icon: BookOpen, tone: "green" },
  { label: "Google Slides", detail: "Use decks as source material", icon: Layers3, tone: "amber" },
] as const;

const ACTIONS: Array<{
  id: string;
  label: string;
  detail: string;
  icon: LucideIcon;
  tone: string;
  prompt?: string;
  studio?: StudioOutput["output_type"];
  available?: boolean;
  unavailableReason?: string;
}> = [
  { id: "report", label: "Generate a report", detail: "Turn ready sources into a cited deliverable", icon: FileText, tone: "coral", studio: "report" },
  { id: "summary", label: "Summarize", detail: "Get the clearest version of your sources", icon: WandSparkles, tone: "blue", prompt: "Summarize the key ideas across my sources and cite every important claim." },
  { id: "explain", label: "Explain a concept", detail: "Break something complex into steps", icon: Lightbulb, tone: "amber", prompt: "Explain the most important concept in my sources step by step, with a real-world example." },
  { id: "compare", label: "Compare sources", detail: "See where approaches agree or differ", icon: Network, tone: "violet", prompt: "Compare the main approaches across my sources. Show agreement, disagreement, and why it matters." },
  { id: "insights", label: "Find insights", detail: "Surface trends, metrics, and opportunities", icon: BrainCircuit, tone: "green", prompt: "Extract the strongest trends, metrics, hidden opportunities, and open questions from my sources." },
  { id: "study", label: "Make a study guide", detail: "Planned after the Report milestone", icon: BookOpen, tone: "blue", available: false, unavailableReason: "Study tools will be enabled after the notebook-to-report review." },
  { id: "flashcards", label: "Create flashcards", detail: "Planned after the Report milestone", icon: Layers3, tone: "violet", available: false, unavailableReason: "Flashcards will be enabled after the notebook-to-report review." },
  { id: "quiz", label: "Build a practice quiz", detail: "Planned after the Report milestone", icon: Check, tone: "amber", available: false, unavailableReason: "Quizzes will be enabled after the notebook-to-report review." },
  { id: "business", label: "Make an executive brief", detail: "Decisions, risks, and next steps", icon: PanelRight, tone: "green", prompt: "Create an executive summary with decisions, risks, opportunities, and recommended next steps. Cite the source for each claim." },
  { id: "writing", label: "Strengthen my writing", detail: "Check arguments and generate citations", icon: Quote, tone: "coral", prompt: "Review the argument I am working toward using my sources. Identify weak links, missing evidence, and suggest citation-backed improvements." },
  { id: "questions", label: "Prepare discussion questions", detail: "Useful prompts for class or meetings", icon: MessageCircle, tone: "blue", prompt: "Create thoughtful discussion questions from my sources, including suggested answers with citations." },
];

function normalizeStatus(status?: string): SourceStatus {
  if (status === "pending" || status === "processing" || status === "failed") return status;
  return "ready";
}

function sourceIcon(type: string): LucideIcon {
  const kind = type.toLowerCase();
  if (kind.includes("youtube")) return Video;
  if (kind.includes("audio")) return FileAudio;
  if (kind.includes("url") || kind.includes("web")) return Globe2;
  return FileText;
}

function sourceTone(type: string): string {
  const kind = type.toLowerCase();
  if (kind.includes("youtube")) return "red";
  if (kind.includes("audio")) return "violet";
  if (kind.includes("url") || kind.includes("web")) return "blue";
  if (kind.includes("docx") || kind.includes("pptx")) return "amber";
  return "coral";
}

function formatDate(value?: string) {
  if (!value) return "";
  return new Date(value).toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

function formatDuration(seconds: number) {
  const minutes = Math.floor(seconds / 60);
  const remainder = Math.floor(seconds % 60).toString().padStart(2, "0");
  return `${minutes}:${remainder}`;
}

function outputLabel(value: string) {
  return value.replace(/_/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function messageCitations(value: unknown): Citation[] | undefined {
  if (!Array.isArray(value)) return undefined;
  return value as Citation[];
}

function errorMessage(error: unknown, fallback: string) {
  if (!(error instanceof Error) || !error.message) return fallback;
  const json = error.message.match(/(\{.*\})/);
  if (json) {
    try {
      const payload = JSON.parse(json[1]) as { detail?: string };
      if (payload.detail) return payload.detail;
    } catch {
      // Keep the transport error when the body is not JSON.
    }
  }
  return error.message;
}

export default function Dashboard() {
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [newWorkspaceName, setNewWorkspaceName] = useState("");
  const [sources, setSources] = useState<Source[]>([]);
  const [messages, setMessages] = useState<Message[]>([]);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [input, setInput] = useState("");
  const [panel, setPanel] = useState<Panel>("workspace");
  const [answerMode, setAnswerMode] = useState<AnswerMode>("auto");
  const [sourceFilter, setSourceFilter] = useState<SourceFilter>("all");
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(false);
  const [streaming, setStreaming] = useState("");
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const [engine, setEngine] = useState<"checking" | "cloud" | "local">("checking");
  const [showSourceComposer, setShowSourceComposer] = useState(false);
  const [showWorkspaceMenu, setShowWorkspaceMenu] = useState(false);
  const [selectedCitation, setSelectedCitation] = useState<Citation | null>(null);
  const [selectedSource, setSelectedSource] = useState<Source | null>(null);
  const [sourcePreview, setSourcePreview] = useState<SourcePreview | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [selectedOutput, setSelectedOutput] = useState<StudioOutput | null>(null);
  const [outputs, setOutputs] = useState<StudioOutput[]>([]);
  const [generatingOutput, setGeneratingOutput] = useState<string | null>(null);
  const [audio, setAudio] = useState<AudioOverview | null>(null);
  const audioLoading = false;
  const audioUrl: string | null = null;
  const [audioPlaying, setAudioPlaying] = useState(false);
  const [sourceInput, setSourceInput] = useState("");
  const [sourceTextTitle, setSourceTextTitle] = useState("");
  const [sourceText, setSourceText] = useState("");
  const [sourceMode, setSourceMode] = useState<"files" | "link" | "text">("files");
  const [sourceBusy, setSourceBusy] = useState(false);
  const [citationMap, setCitationMap] = useState<Record<string, Citation>>({});
  const [streamingHasSources, setStreamingHasSources] = useState(false);
  const [layout, setLayout] = useState<LayoutState>(DEFAULT_LAYOUT);
  const [layoutLoaded, setLayoutLoaded] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const audioRef = useRef<HTMLAudioElement>(null);
  const citationMapRef = useRef<Record<string, Citation>>({});
  const resizeRef = useRef<{ panel: "source" | "output"; startX: number; startWidth: number } | null>(null);

  const readySources = useMemo(() => sources.filter((source) => source.status === "ready"), [sources]);
  const processingSources = useMemo(
    () => sources.filter((source) => source.status === "pending" || source.status === "processing"),
    [sources],
  );
  const visibleSources = useMemo(() => {
    const query = search.trim().toLowerCase();
    return sources.filter((source) => {
      const matchesFilter = sourceFilter === "all"
        || (sourceFilter === "ready" && source.status === "ready")
        || (sourceFilter === "processing" && (source.status === "pending" || source.status === "processing"));
      const matchesQuery = !query || `${source.filename} ${source.file_type}`.toLowerCase().includes(query);
      return matchesFilter && matchesQuery;
    });
  }, [search, sourceFilter, sources]);

  const setWorkspaceAndPersist = useCallback((next: Workspace) => {
    setWorkspace(next);
    setSources([]);
    setOutputs([]);
    setMessages([]);
    setSessionId(null);
    setAudio(null);
    setSelectedOutput(null);
    setLayout(DEFAULT_LAYOUT);
    setLayoutLoaded(false);
    if (typeof window !== "undefined") window.localStorage.setItem("atlas:selected-workspace", next.id);
  }, []);

  const resizePanel = useCallback((panel: "source" | "output", width: number) => {
    const bounded = Math.max(240, Math.min(520, Math.round(width)));
    setLayout((current) => panel === "source"
      ? { ...current, source_panel_width: bounded }
      : { ...current, output_panel_width: bounded });
  }, []);

  const resetLayout = useCallback(async () => {
    setLayout(DEFAULT_LAYOUT);
    setLayoutLoaded(true);
    if (workspace) await apiClient.del(`/api/v1/workspaces/${workspace.id}/layout`).catch(() => undefined);
    setNotice("Atlas layout reset.");
  }, [workspace]);

  useEffect(() => {
    if (!workspace) return;
    let active = true;
    void apiClient.get<{ layout?: LayoutState }>(`/api/v1/workspaces/${workspace.id}/layout`)
      .then((data) => { if (active && data.layout) setLayout({ ...DEFAULT_LAYOUT, ...data.layout }); })
      .catch(() => undefined)
      .finally(() => { if (active) setLayoutLoaded(true); });
    return () => { active = false; };
  }, [workspace]);

  useEffect(() => {
    if (!workspace || !layoutLoaded) return;
    const timer = window.setTimeout(() => {
      void apiClient.put(`/api/v1/workspaces/${workspace.id}/layout`, { layout }).catch(() => undefined);
    }, 500);
    return () => window.clearTimeout(timer);
  }, [layout, layoutLoaded, workspace]);

  useEffect(() => {
    const move = (event: PointerEvent) => {
      const active = resizeRef.current;
      if (!active) return;
      const delta = active.panel === "source" ? event.clientX - active.startX : active.startX - event.clientX;
      resizePanel(active.panel, active.startWidth + delta);
    };
    const end = () => {
      resizeRef.current = null;
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", end);
    return () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", end);
    };
  }, [resizePanel]);

  const beginResize = (event: React.PointerEvent<HTMLButtonElement>, panel: "source" | "output") => {
    event.preventDefault();
    resizeRef.current = {
      panel,
      startX: event.clientX,
      startWidth: panel === "source" ? layout.source_panel_width : layout.output_panel_width,
    };
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
  };

  const keyboardResize = (event: React.KeyboardEvent<HTMLButtonElement>, panel: "source" | "output") => {
    const current = panel === "source" ? layout.source_panel_width : layout.output_panel_width;
    if (event.key === "ArrowLeft" || event.key === "ArrowRight") {
      event.preventDefault();
      resizePanel(panel, current + (event.key === "ArrowRight" ? 16 : -16) * (panel === "source" ? 1 : -1));
    }
    if (event.key === "Home" || event.key === "End") {
      event.preventDefault();
      resizePanel(panel, event.key === "Home" ? 240 : 520);
    }
  };

  const createWorkspace = useCallback(async (name: string) => {
    const created = await apiClient.post<Workspace>("/api/v1/workspaces", { name });
    setWorkspaces((current) => [created, ...current.filter((item) => item.id !== created.id)]);
    setWorkspaceAndPersist(created);
    return created;
  }, [setWorkspaceAndPersist]);

  const loadWorkspaces = useCallback(async () => {
    try {
      const data = await apiClient.get<Workspace[]>("/api/v1/workspaces");
      if (!data.length) {
        await createWorkspace("My first workspace");
        return;
      }
      setWorkspaces(data);
      const savedId = typeof window !== "undefined" ? window.localStorage.getItem("atlas:selected-workspace") : null;
      setWorkspaceAndPersist(data.find((item) => item.id === savedId) || data[0]);
    } catch (caught) {
      setError(errorMessage(caught, "Atlas could not load your workspace."));
    }
  }, [createWorkspace, setWorkspaceAndPersist]);

  const loadSources = useCallback(async (workspaceId: string) => {
    const data = await apiClient.get<Source[]>(`/api/v1/workspaces/${workspaceId}/documents`);
    setSources(data.map((source) => ({ ...source, status: normalizeStatus(source.status) })));
  }, []);

  const loadOutputs = useCallback(async (workspaceId: string) => {
    const data = await apiClient.get<StudioOutput[]>(`/api/v1/workspaces/${workspaceId}/studio`);
    setOutputs(data);
  }, []);

  const ensureSession = useCallback(async (workspaceId: string) => {
    if (sessionId) return sessionId;
    const existing = await apiClient.get<Array<{ id: string; title: string }>>(`/api/v1/workspaces/${workspaceId}/sessions`);
    const active = existing[0] || await apiClient.post<{ id: string }>(`/api/v1/workspaces/${workspaceId}/sessions`, { title: "Ask Atlas" });
    setSessionId(active.id);
    return active.id;
  }, [sessionId]);

  useEffect(() => {
    const workspaceTimer = window.setTimeout(() => void loadWorkspaces(), 0);
    const engineTimer = window.setTimeout(() => {
      void apiClient.get<{ providers: Array<{ id: string; status: string }> }>("/api/v1/settings/providers")
        .then((data) => setEngine(data.providers.some((provider) => provider.id === "atlas-cloud" && provider.status === "active") ? "cloud" : "local"))
        .catch(() => setEngine("local"));
    }, 0);
    return () => {
      window.clearTimeout(workspaceTimer);
      window.clearTimeout(engineTimer);
    };
  }, [loadWorkspaces]);

  useEffect(() => {
    if (!workspace) return;
    const timer = window.setTimeout(() => {
      void Promise.all([loadSources(workspace.id), loadOutputs(workspace.id)]).catch((caught) => {
        setError(errorMessage(caught, "Atlas could not load this workspace."));
      });
    }, 0);
    return () => window.clearTimeout(timer);
  }, [loadOutputs, loadSources, workspace]);

  useEffect(() => {
    if (!workspace || !processingSources.length) return;
    const timer = window.setInterval(() => {
      void loadSources(workspace.id);
    }, 3000);
    return () => window.clearInterval(timer);
  }, [loadSources, processingSources.length, workspace]);

  useEffect(() => {
    if (!workspace || !outputs.some((output) => output.status === "pending" || output.status === "processing")) return;
    const timer = window.setInterval(() => {
      void loadOutputs(workspace.id);
    }, 3500);
    return () => window.clearInterval(timer);
  }, [loadOutputs, outputs, workspace]);

  useEffect(() => {
    if (!sessionId) return;
    void apiClient.get<{ messages?: Array<{ id: string; role: string; content: string; citations?: unknown }> }>(`/api/v1/sessions/${sessionId}`)
      .then((data) => setMessages((data.messages || []).map((message) => ({
        id: message.id,
        role: message.role === "user" ? "user" : "assistant",
        content: message.content,
        citations: messageCitations(message.citations),
      }))))
      .catch((caught) => setError(errorMessage(caught, "Atlas could not load this conversation.")));
  }, [sessionId]);

  const sendMessage = useCallback(async (event?: FormEvent, prompt?: string) => {
    event?.preventDefault();
    const content = (prompt || input).trim();
    if (!content || loading || !workspace) return;
    setInput("");
    setError("");
    setNotice("");
    setLoading(true);
    setStreaming("");
    setStreamingHasSources(false);
    citationMapRef.current = {};
    setCitationMap({});
    const userMessage: Message = { id: crypto.randomUUID(), role: "user", content };
    setMessages((current) => [...current, userMessage]);
    try {
      const activeSessionId = await ensureSession(workspace.id);
      const response = await apiClient.stream(`/api/v1/sessions/${activeSessionId}/chat/stream`, {
        content,
        mode: answerMode,
      });
      const reader = response.body?.getReader();
      if (!reader) throw new Error("Atlas did not return a readable response.");
      const decoder = new TextDecoder();
      let buffer = "";
      let accumulated = "";
      let finished = false;
      while (!finished) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";
        for (const line of lines) {
          const clean = line.trim();
          if (!clean.startsWith("data: ")) continue;
          const raw = clean.slice(6);
          if (raw === "[DONE]") {
            finished = true;
            break;
          }
          try {
            const payload = JSON.parse(raw) as {
              type?: string;
              content?: string;
              sources?: Record<string, Citation>;
              has_source_context?: boolean;
            };
            if (payload.type === "metadata" && payload.sources) {
              citationMapRef.current = payload.sources;
              setCitationMap(payload.sources);
            }
            if (payload.type === "metadata") {
              setStreamingHasSources(Boolean(payload.has_source_context));
            }
            if (payload.type === "chunk") {
              accumulated += payload.content || "";
              setStreaming(accumulated);
            }
          } catch {
            // Ignore partial SSE frames and keep reading.
          }
        }
      }
      const assistant = accumulated.trim() || "Atlas did not return an answer. Try asking in a different way.";
      setMessages((current) => [...current, {
        id: crypto.randomUUID(),
        role: "assistant",
        content: assistant,
        citations: Object.values(citationMapRef.current),
      }]);
      setStreaming("");
      setStreamingHasSources(Object.keys(citationMapRef.current).length > 0);
    } catch (caught) {
      setError(errorMessage(caught, "Atlas could not answer that question."));
      setStreaming("");
    } finally {
      setLoading(false);
    }
  }, [answerMode, ensureSession, input, loading, workspace]);

  const handleFiles = async (files: FileList | null) => {
    if (!files || !workspace) return;
    setSourceBusy(true);
    setError("");
    setNotice("");
    try {
      for (const file of Array.from(files)) {
        const form = new FormData();
        form.append("file", file);
        await apiClient.postForm<Source>(`/api/v1/workspaces/${workspace.id}/documents`, form);
      }
      setNotice(`${files.length} source${files.length === 1 ? "" : "s"} added. Atlas is indexing the material now.`);
      await loadSources(workspace.id);
      setShowSourceComposer(false);
    } catch (caught) {
      setError(errorMessage(caught, "Atlas could not add that source."));
    } finally {
      setSourceBusy(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  const handleUrl = async (event: FormEvent) => {
    event.preventDefault();
    if (!workspace || !sourceInput.trim()) return;
    setSourceBusy(true);
    setError("");
    try {
      const isYoutube = /(?:youtube\.com|youtu\.be)/i.test(sourceInput);
      const path = isYoutube
        ? `/api/v1/workspaces/${workspace.id}/documents/youtube`
        : `/api/v1/workspaces/${workspace.id}/documents/url`;
      await apiClient.post<Source>(path, { url: sourceInput.trim() });
      setNotice("Source added. Atlas is preparing it for grounded answers.");
      setSourceInput("");
      await loadSources(workspace.id);
      setShowSourceComposer(false);
    } catch (caught) {
      setError(errorMessage(caught, "Atlas could not reach that link."));
    } finally {
      setSourceBusy(false);
    }
  };

  const handleText = async (event: FormEvent) => {
    event.preventDefault();
    if (!workspace || !sourceText.trim() || !sourceTextTitle.trim()) return;
    setSourceBusy(true);
    setError("");
    try {
      await apiClient.post<Source>(`/api/v1/workspaces/${workspace.id}/documents/text`, {
        title: sourceTextTitle.trim(),
        content: sourceText.trim(),
      });
      setNotice("Your notes are now part of the Atlas knowledge base.");
      setSourceTextTitle("");
      setSourceText("");
      await loadSources(workspace.id);
      setShowSourceComposer(false);
    } catch (caught) {
      setError(errorMessage(caught, "Atlas could not add that text."));
    } finally {
      setSourceBusy(false);
    }
  };

  const deleteSource = async (sourceId: string) => {
    try {
      await apiClient.del(`/api/v1/documents/${sourceId}`);
      setSources((current) => current.filter((source) => source.id !== sourceId));
      setNotice("Source removed from this workspace.");
    } catch (caught) {
      setError(errorMessage(caught, "Atlas could not remove that source."));
    }
  };

  const openSourcePreview = async (source: Source) => {
    setSelectedSource(source);
    setSourcePreview(null);
    setPreviewLoading(true);
    try {
      const preview = await apiClient.get<SourcePreview>(`/api/v1/documents/${source.id}/preview`);
      setSourcePreview(preview);
    } catch (caught) {
      setError(errorMessage(caught, "Atlas could not open the indexed source text."));
    } finally {
      setPreviewLoading(false);
    }
  };

  const createOutput = async (type: StudioOutput["output_type"]) => {
    if (!workspace || !readySources.length) {
      setError("Add and finish indexing at least one source before creating a study tool.");
      setPanel("sources");
      return;
    }
    setGeneratingOutput(type);
    setError("");
    try {
      const output = await apiClient.post<StudioOutput>(`/api/v1/workspaces/${workspace.id}/studio`, {
        output_type: type,
        title: `Atlas ${outputLabel(type)}`,
        source_ids: readySources.map((source) => source.id),
        length: "standard",
      });
      setOutputs((current) => [output, ...current.filter((item) => item.id !== output.id)]);
      setSelectedOutput(output);
      setPanel("outputs");
      setNotice(output.status === "ready"
        ? `${outputLabel(type)} is ready. Open it here to use it.`
        : `${outputLabel(type)} is queued. Atlas will show the result here when it finishes.`);
    } catch (caught) {
      setError(errorMessage(caught, "Atlas could not create that output."));
    } finally {
      setGeneratingOutput(null);
    }
  };

  const createAudio = async () => {
    setNotice("Audio overview will be enabled after the Report milestone.");
    setPanel("outputs");
  };

  const handleAction = (action: (typeof ACTIONS)[number]) => {
    if (action.available === false) {
      setNotice(action.unavailableReason || "This Atlas capability is not enabled yet.");
      setPanel("outputs");
      return;
    }
    if (action.studio) {
      void createOutput(action.studio);
      return;
    }
    if (action.prompt) {
      setPanel("workspace");
      setInput(action.prompt);
      window.setTimeout(() => void sendMessage(undefined, action.prompt), 0);
    }
  };

  const createNewWorkspace = async (event: FormEvent) => {
    event.preventDefault();
    if (!newWorkspaceName.trim()) return;
    try {
      await createWorkspace(newWorkspaceName.trim());
      setNewWorkspaceName("");
      setShowWorkspaceMenu(false);
    } catch (caught) {
      setError(errorMessage(caught, "Atlas could not create that workspace."));
    }
  };

  const renderOutputContent = (output: StudioOutput) => {
    if (output.output_type === "report" && typeof output.content === "string") {
      const citations = output.citations || [];
      return <div className="output-report-markdown">{output.content.split(/(\[source_\d+\])/g).map((part, index) => {
        const match = part.match(/^\[source_(\d+)\]$/);
        if (!match) return <span key={index}>{part}</span>;
        const citation = citations[Number(match[1]) - 1];
        return <button type="button" className="citation-chip" key={index} onClick={() => citation && setSelectedCitation(citation)} disabled={!citation}><Quote size={12} /> {citation?.filename || `Source ${match[1]}`}</button>;
      })}</div>;
    }
    if (typeof output.content === "string") {
      return <pre className="output-markdown">{output.content}</pre>;
    }
    const content = output.content || {};
    const records = (value: unknown): Array<Record<string, unknown>> => (
      Array.isArray(value)
        ? value.filter((item): item is Record<string, unknown> => Boolean(item) && typeof item === "object")
        : []
    );
    const strings = (value: unknown): string[] => (
      Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : []
    );

    if (output.output_type === "study_guide") {
      return <div className="structured-output study-guide-output">{records(content.sections).map((section, index) => <article className="output-section" key={index}><span className="output-section-number">{String(index + 1).padStart(2, "0")}</span><div><h3>{String(section.heading || "Section")}</h3><p>{String(section.summary || "")}</p>{strings(section.key_points).length > 0 && <ul>{strings(section.key_points).map((point, pointIndex) => <li key={pointIndex}>{point}</li>)}</ul>}</div></article>)}</div>;
    }
    if (output.output_type === "flashcards") {
      return <div className="flashcards-output">{records(content.cards).map((card, index) => <article className="flashcard" key={index}><span>Card {index + 1}</span><strong>{String(card.front || "Question")}</strong><p>{String(card.back || "Answer")}</p></article>)}</div>;
    }
    if (output.output_type === "quiz") {
      return <div className="quiz-output">{records(content.questions).map((question, index) => { const choices = strings(question.choices); const answerIndex = Number(question.answer_index); return <article className="quiz-question" key={index}><span>Question {index + 1}</span><h3>{String(question.question || "")}</h3><div className="quiz-choices">{choices.map((choice, choiceIndex) => <div className={choiceIndex === answerIndex ? "correct" : ""} key={choiceIndex}><b>{String.fromCharCode(65 + choiceIndex)}</b>{choice}{choiceIndex === answerIndex && <Check size={14} />}</div>)}</div><p className="quiz-explanation">{String(question.explanation || "")}</p></article>; })}</div>;
    }
    if (output.output_type === "mind_map") {
      return <div className="mind-map-output"><div className="mind-map-root"><Sparkles size={16} /> {String(content.root || "Source map")}</div><div className="mind-map-branches">{records(content.branches).map((branch, index) => <article key={index}><strong>{String(branch.label || "Branch")}</strong>{strings(branch.children).map((child, childIndex) => <span key={childIndex}>{child}</span>)}</article>)}</div></div>;
    }
    return <pre className="output-markdown">{JSON.stringify(content, null, 2)}</pre>;
  };

  const renderMessage = (message: Message) => {
    const parts = message.content.split(/(\[source_\d+\])/g);
    const citations = message.citations || [];
    return parts.map((part, index) => {
      const match = part.match(/^\[source_(\d+)\]$/);
      if (!match) return <span key={`${message.id}-${index}`}>{part}</span>;
      const citation = citations[Number(match[1])] || citationMap[`source_${match[1]}`];
      return (
        <button
          key={`${message.id}-${index}`}
          type="button"
          className="citation-chip"
          onClick={() => citation && setSelectedCitation(citation)}
          disabled={!citation}
        >
          <Quote size={12} /> {citation?.filename || `Source ${Number(match[1]) + 1}`}
        </button>
      );
    });
  };

  return (
    <div
      className={`atlas-shell ${layout.source_panel_collapsed ? "source-panel-collapsed" : ""} ${layout.output_panel_collapsed ? "output-panel-collapsed" : ""}`}
      style={{ "--atlas-source-panel-width": `${layout.source_panel_width}px`, "--atlas-output-panel-width": `${layout.output_panel_width}px` } as CSSProperties}
    >
      <aside className="atlas-sidebar">
        <div className="atlas-brand-row">
          <Link href="/" className="atlas-brand" aria-label="Atlas home">
            <span className="atlas-brand-mark"><span /><span /><span /></span>
            <span>Atlas <em>LM</em></span>
          </Link>
          <button type="button" className="layout-toggle" onClick={() => setLayout((current) => ({ ...current, source_panel_collapsed: !current.source_panel_collapsed }))} aria-label={layout.source_panel_collapsed ? "Restore source panel" : "Collapse source panel"}>
            {layout.source_panel_collapsed ? <ChevronRight size={15} /> : <ChevronLeft size={15} />}
          </button>
        </div>

        {!layout.source_panel_collapsed && <>

        <div className="workspace-switcher">
          <button type="button" className="workspace-switcher-button" onClick={() => setShowWorkspaceMenu((value) => !value)}>
            <span className="workspace-avatar">{workspace?.name.slice(0, 1).toUpperCase() || "A"}</span>
            <span className="workspace-switcher-copy"><small>Workspace</small><strong>{workspace?.name || "Loading..."}</strong></span>
            <ChevronDown size={15} />
          </button>
          {showWorkspaceMenu && (
            <div className="workspace-menu">
              {workspaces.map((item) => (
                <button key={item.id} type="button" className={`workspace-menu-item ${workspace?.id === item.id ? "selected" : ""}`} onClick={() => { setWorkspaceAndPersist(item); setShowWorkspaceMenu(false); }}>
                  <span>{item.name}</span>
                  {workspace?.id === item.id && <Check size={14} />}
                </button>
              ))}
              <form className="new-workspace-form" onSubmit={createNewWorkspace}>
                <input value={newWorkspaceName} onChange={(event) => setNewWorkspaceName(event.target.value)} placeholder="New workspace" />
                <button type="submit" aria-label="Create workspace"><Plus size={15} /></button>
              </form>
            </div>
          )}
        </div>

        <nav className="atlas-nav" aria-label="Atlas workspace">
          <button type="button" className={`atlas-nav-item ${panel === "workspace" ? "active" : ""}`} onClick={() => setPanel("workspace")}><Sparkles size={17} /><span>Ask Atlas</span><kbd>1</kbd></button>
          <button type="button" className={`atlas-nav-item ${panel === "sources" ? "active" : ""}`} onClick={() => setPanel("sources")}><FolderOpen size={17} /><span>Sources</span><b>{sources.length}</b></button>
          <button type="button" className={`atlas-nav-item ${panel === "outputs" ? "active" : ""}`} onClick={() => setPanel("outputs")}><WandSparkles size={17} /><span>Outputs</span><b>{outputs.length}</b></button>
          <button type="button" className={`atlas-nav-item unavailable ${panel === "audio" ? "active" : ""}`} disabled title="Audio overview will be enabled after the Report milestone."><Headphones size={17} /><span>Audio overview</span><b>Planned</b></button>
        </nav>

        <div className="sidebar-source-note">
          <div className="sidebar-note-orbit"><Sparkles size={15} /></div>
          <strong>Your sources, one mind.</strong>
          <p>Atlas connects documents, links, lectures, and research into one citable knowledge base.</p>
        </div>

        <div className="atlas-sidebar-footer">
          <div className="engine-row"><span className={`engine-dot ${engine}`} /><span>{engine === "cloud" ? "Atlas AI is ready" : engine === "local" ? "Local Atlas engine" : "Checking AI engine"}</span></div>
          <Link href="/settings/workspace" className="settings-link">Workspace settings <ArrowUpRight size={14} /></Link>
        </div>
        </>}
        {!layout.source_panel_collapsed && <button type="button" className="layout-reset-button" onClick={() => void resetLayout()}>Reset layout</button>}
        <button type="button" className="layout-resize-handle layout-resize-source" onPointerDown={(event) => beginResize(event, "source")} onKeyDown={(event) => keyboardResize(event, "source")} aria-label="Resize left panel" aria-valuemin={240} aria-valuemax={520} aria-valuenow={layout.source_panel_width} role="separator" tabIndex={0} />
      </aside>

      <main className="atlas-main">
        <header className="atlas-topbar">
          <div className="breadcrumb"><span>Atlas</span><ChevronRight size={14} /><strong>{workspace?.name || "Workspace"}</strong></div>
          <div className="topbar-actions"><span className="privacy-pill"><Cloud size={14} /> Private workspace</span><button type="button" className="topbar-avatar" title="Account">P</button></div>
        </header>

        {error && <div className="atlas-alert error"><CircleAlert size={16} /><span>{error}</span><button type="button" onClick={() => setError("")}><X size={15} /></button></div>}
        {notice && <div className="atlas-alert success"><Check size={16} /><span>{notice}</span><button type="button" onClick={() => setNotice("")}><X size={15} /></button></div>}

        {panel === "workspace" && (
          <section className="workspace-page">
            <div className="workspace-intro">
              <div>
                <p className="eyebrow"><span className="eyebrow-dot" /> Source-aware intelligence</p>
                <h1>What are you working on?</h1>
                <p className="intro-copy">Ask Atlas anything. It can use your sources when they help, answer from its general knowledge when they do not, and show you which is which.</p>
              </div>
              <div className="intro-stats"><span><strong>{readySources.length}</strong> ready sources</span><span><strong>{messages.filter((message) => message.role === "assistant").length}</strong> answers</span></div>
            </div>

            <div className="ask-card">
              <div className="ask-card-top"><span className="ask-orb"><Sparkles size={18} /></span><div><strong>Ask Atlas</strong><span>General knowledge plus source citations</span></div><span className="ask-card-status">{answerMode === "sources" ? "Sources only" : answerMode === "general" ? "Atlas knowledge" : "Auto"}</span></div>
              <form className="ask-form" onSubmit={(event) => void sendMessage(event)}>
                <div className="answer-mode-picker" aria-label="Answer mode">
                  <span>Answer with</span>
                  <button type="button" className={answerMode === "auto" ? "selected" : ""} onClick={() => setAnswerMode("auto")}>Auto</button>
                  <button type="button" className={answerMode === "sources" ? "selected" : ""} onClick={() => setAnswerMode("sources")}>My sources only</button>
                  <button type="button" className={answerMode === "general" ? "selected" : ""} onClick={() => setAnswerMode("general")}>General knowledge</button>
                </div>
                <textarea value={input} onChange={(event) => setInput(event.target.value)} placeholder={answerMode === "sources" ? "Ask a question about your sources..." : "Ask Atlas anything..."} rows={3} disabled={loading} />
                <div className="ask-form-footer"><span>Try: &quot;What matters most across these sources?&quot;</span><button type="submit" disabled={!input.trim() || loading}><span>{loading ? "Thinking" : "Ask Atlas"}</span>{loading ? <Loader2 size={16} className="spin" /> : <Send size={16} />}</button></div>
              </form>
            </div>

            {messages.length > 0 || streaming ? (
              <div className="conversation-card">
                <div className="section-heading"><div><p className="eyebrow">Conversation</p><h2>Working with Atlas</h2></div><button type="button" className="quiet-button" onClick={() => setMessages([])}>Clear</button></div>
                <div className="conversation-list">
                  {messages.map((message) => <div className={`message-row ${message.role}`} key={message.id}><span className={`message-avatar ${message.role}`}>{message.role === "assistant" ? <Sparkles size={15} /> : "P"}</span><div className="message-body"><div className="message-meta">{message.role === "assistant" ? "Atlas" : "You"}<span>{message.role === "assistant" ? (message.citations?.length ? "From your sources" : "General knowledge") : ""}</span></div><div className="message-copy">{renderMessage(message)}</div></div></div>)}
                  {streaming && <div className="message-row assistant"><span className="message-avatar assistant"><Sparkles size={15} /></span><div className="message-body"><div className="message-meta">Atlas<span>{streamingHasSources ? "Reading your sources" : "General knowledge"}</span></div><div className="message-copy">{renderMessage({ id: "stream", role: "assistant", content: streaming })}<span className="typing-caret" /></div></div></div>}
                </div>
              </div>
            ) : (
            <div className="start-area"><div className="start-area-heading"><div><p className="eyebrow">Start with a job</p><h2>Make your sources useful</h2></div><span>Atlas can handle the rest</span></div><div className="action-grid">{ACTIONS.map((action) => { const Icon = action.icon; return <button type="button" key={action.id} className={`action-card tone-${action.tone} ${action.available === false ? "unavailable" : ""}`} onClick={() => handleAction(action)} disabled={Boolean(generatingOutput)} title={action.available === false ? action.unavailableReason : undefined}><span className="action-icon"><Icon size={17} /></span><span className="action-copy"><strong>{action.label}</strong><small>{action.detail}</small></span>{action.available === false ? <span className="planned-badge">Planned</span> : <ChevronRight size={16} className="action-arrow" />}</button>; })}</div></div>
            )}
          </section>
        )}

        {panel === "sources" && (
         <section className="panel-page"><div className="panel-page-heading"><div><p className="eyebrow">Knowledge base</p><h1>Your sources</h1><p>Add the material Atlas should understand. PDFs, websites, videos, audio, Google files, and course notes all work together here.</p></div><button type="button" className="primary-button" onClick={() => setShowSourceComposer(true)}><Plus size={17} /> Add sources</button></div><div className="source-type-strip">{SOURCE_TYPES.map((type) => { const Icon = type.icon; return <div className={`source-type-card tone-${type.tone}`} key={type.label}><span className="source-type-icon"><Icon size={17} /></span><div><strong>{type.label}</strong><small>{type.detail}</small></div></div>; })}</div><div className="source-library"><div className="library-toolbar"><div className="library-tabs"><button type="button" className={sourceFilter === "all" ? "selected" : ""} onClick={() => setSourceFilter("all")}>All <b>{sources.length}</b></button><button type="button" className={sourceFilter === "ready" ? "selected" : ""} onClick={() => setSourceFilter("ready")}>Ready <b>{readySources.length}</b></button><button type="button" className={sourceFilter === "processing" ? "selected" : ""} onClick={() => setSourceFilter("processing")}>Indexing <b>{processingSources.length}</b></button></div><label className="search-field"><Search size={15} /><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search sources" /></label></div>{visibleSources.length ? <div className="source-table">{visibleSources.map((source) => { const Icon = sourceIcon(source.file_type); const busy = source.status === "pending" || source.status === "processing"; return <div className="source-row" key={source.id}><span className={`source-row-icon tone-${sourceTone(source.file_type)}`}>{busy ? <Loader2 size={17} className="spin" /> : <Icon size={17} />}</span><div className="source-row-main"><strong>{source.filename}</strong><span>{source.file_type.toUpperCase()} <i /> {busy ? "Indexing" : source.status === "failed" ? "Needs attention" : "Ready for Atlas"} <i /> {formatDate(source.created_at)}</span>{source.error_message && <small className="source-error">{source.error_message}</small>}</div><button type="button" className="source-preview-button" onClick={() => void openSourcePreview(source)} disabled={busy}>{busy ? "Indexing" : "View indexed text"}</button><div className={`source-status ${source.status}`}>{busy ? "Preparing" : source.status === "failed" ? "Failed" : "Ready"}</div><button type="button" className="icon-button danger-on-hover" title="Remove source" onClick={() => void deleteSource(source.id)}><Trash2 size={16} /></button></div>; })}</div> : <div className="empty-library"><FolderOpen size={28} /><h3>No sources match this view</h3><p>Add your first PDF, website, lecture, or research paper and Atlas will turn it into a searchable knowledge base.</p><button type="button" className="secondary-button" onClick={() => setShowSourceComposer(true)}><UploadCloud size={16} /> Add a source</button></div>}</div></section>
        )}

        {panel === "outputs" && (
         <section className="panel-page"><div className="panel-page-heading"><div><p className="eyebrow">Generated with your sources</p><h1>Outputs</h1><p>Study tools, structured thinking, and useful deliverables made from the material in this workspace.</p></div><button type="button" className="primary-button" onClick={() => setPanel("workspace")}><Sparkles size={17} /> Ask Atlas</button></div><div className="output-layout"><div className="output-list"><div className="output-list-heading"><span>Created outputs</span><span>{outputs.length}</span></div>{outputs.length ? outputs.map((output) => <button type="button" key={output.id} className={`output-item ${selectedOutput?.id === output.id ? "selected" : ""}`} onClick={() => setSelectedOutput(output)}><span className="output-item-icon tone-violet"><WandSparkles size={16} /></span><span><strong>{output.title}</strong><small>{outputLabel(output.output_type)} <i /> {output.status === "ready" ? "Ready" : output.status === "failed" ? "Failed" : "Building"}</small></span>{output.status === "pending" || output.status === "processing" ? <Loader2 size={15} className="spin" /> : output.status === "failed" ? <CircleAlert size={15} /> : <ChevronRight size={16} />}</button>) : <div className="output-empty"><WandSparkles size={22} /><strong>Nothing generated yet</strong><span>Choose a study tool below to create your first output.</span></div>}<div className="output-create-list">{ACTIONS.filter((action) => action.studio).map((action) => { const Icon = action.icon; const type = action.studio as StudioOutput["output_type"]; return <button type="button" key={action.id} className="output-create-button" onClick={() => void createOutput(type)} disabled={generatingOutput === type}><Icon size={16} /><span>{action.label}</span>{generatingOutput === type ? <Loader2 size={14} className="spin" /> : <Plus size={14} />}</button>; })}</div></div><div className="output-viewer">{selectedOutput ? <><div className="output-viewer-heading"><div><p className="eyebrow">{outputLabel(selectedOutput.output_type)}</p><h2>{selectedOutput.title}</h2></div><button type="button" className="icon-button" onClick={() => setSelectedOutput(null)}><X size={16} /></button></div><div className="output-content">{selectedOutput.status === "failed" ? <div className="output-building"><CircleAlert size={22} /><h3>This output could not be completed</h3><p>{selectedOutput.error || "Atlas could not finish this output. Try again."}</p></div> : selectedOutput.status !== "ready" ? <div className="output-building"><div className="building-orbit"><Sparkles size={22} /></div><h3>Atlas is building this for you</h3><p>It is reading your indexed sources and assembling a citation-backed {outputLabel(selectedOutput.output_type).toLowerCase()}.</p></div> : selectedOutput.content ? renderOutputContent(selectedOutput) : <div className="output-building"><Check size={22} /><h3>Your output is ready</h3><p>Atlas returned an empty result. Try generating it again.</p></div>}</div></> : <div className="viewer-placeholder"><div className="viewer-placeholder-icon"><FileText size={24} /></div><h2>Select an output</h2><p>Your generated study tools and structured notes will appear here.</p></div>}</div></div></section>
        )}

        {panel === "audio" && (
         <section className="panel-page audio-page"><div className="panel-page-heading"><div><p className="eyebrow">Listen to your knowledge base</p><h1>Audio overview</h1><p>Atlas reads your ready sources, writes a short two-host discussion, and returns both an audio track and a transcript you can follow.</p></div><button type="button" className="primary-button" onClick={() => void createAudio()} disabled={audioLoading || !readySources.length}><Headphones size={17} /> {audioLoading ? "Generating..." : "Generate overview"}</button></div><div className="audio-explainer"><div><strong>What this does</strong><p>Useful when you want to review lecture notes, research papers, or a meeting brief while walking. It is not another chat response. It is a narrated summary made from the ready sources shown below.</p></div><span>{readySources.length} ready source{readySources.length === 1 ? "" : "s"} in scope</span></div>{audio ? <div className="audio-layout"><div className="audio-player-card"><div className="audio-art"><div className="audio-art-grid" /><Headphones size={34} /></div><div className="audio-player-copy"><span className="eyebrow">Deep dive</span><h2>{audio.title}</h2><p>{formatDuration(audio.duration)} of narrated source review</p><div className="audio-controls"><button type="button" className="audio-play" disabled={!audioUrl} onClick={() => { const element = audioRef.current; if (!element) return; if (element.paused) { void element.play(); setAudioPlaying(true); } else { element.pause(); setAudioPlaying(false); } }}>{audioPlaying ? "Pause" : <><Play size={16} fill="currentColor" /> {audioUrl ? "Play overview" : "Audio unavailable"}</>}</button><span>{audio.transcript.length} transcript moments</span></div><audio ref={audioRef} src={audioUrl || undefined} onEnded={() => setAudioPlaying(false)} /></div></div><div className="transcript-card"><div className="section-heading"><div><p className="eyebrow">Transcript</p><h2>Follow along</h2></div><span>{audio.style === "deep_dive" ? "Two hosts" : "Brief"}</span></div>{audio.transcript.map((line, index) => <div className="transcript-line" key={`${line.start}-${index}`}><span>{line.name}</span><p>{line.text}{line.cite ? <sup>[{line.cite}]</sup> : null}</p></div>)}</div></div> : <div className="audio-empty"><div className="audio-empty-art"><Mic2 size={30} /></div><h2>Give your sources a voice</h2><p>Generate a narrated summary for research reviews, course materials, meeting prep, or a quick walk through the ideas you have collected.</p><button type="button" className="secondary-button" onClick={() => void createAudio()} disabled={audioLoading || !readySources.length}>{audioLoading ? "Preparing your overview" : readySources.length ? "Create audio overview" : "Add sources first"}</button></div>}</section>
        )}
      </main>

      <button type="button" className="right-rail-toggle" onClick={() => setLayout((current) => ({ ...current, output_panel_collapsed: !current.output_panel_collapsed }))} aria-label={layout.output_panel_collapsed ? "Restore output panel" : "Collapse output panel"}>
        {layout.output_panel_collapsed ? <ChevronLeft size={15} /> : <ChevronRight size={15} />}
      </button>

      <aside className="atlas-right-rail"><div className="right-rail-heading"><div><p className="eyebrow">Workspace pulse</p><h2>At a glance</h2></div><MoreHorizontal size={18} /></div><div className="pulse-card"><div className="pulse-ring"><span>{readySources.length}</span></div><div><strong>Ready to think with</strong><p>{readySources.length ? "Your sources are available to Atlas." : "Add a source to wake up this workspace."}</p></div></div><div className="rail-section"><div className="rail-section-heading"><span>Source types</span><button type="button" onClick={() => setPanel("sources")}>View all</button></div><div className="rail-type-list">{SOURCE_TYPES.slice(0, 4).map((type) => { const Icon = type.icon; const count = sources.filter((source) => source.file_type.toLowerCase().includes(type.label.toLowerCase().replace(/s$/, "").split(" ")[0])).length; return <button type="button" key={type.label} onClick={() => setPanel("sources")}><span className={`rail-type-icon tone-${type.tone}`}><Icon size={15} /></span><span>{type.label}</span><b>{count}</b></button>; })}</div></div><div className="rail-section"><div className="rail-section-heading"><span>Quick actions</span><span className="rail-count">{ACTIONS.length}</span></div><div className="rail-action-list"><button type="button" onClick={() => void createAudio()}><Headphones size={15} /><span>Listen to an overview</span><ChevronRight size={14} /></button><button type="button" onClick={() => handleAction(ACTIONS.find((action) => action.id === "compare")!)}><Network size={15} /><span>Compare approaches</span><ChevronRight size={14} /></button><button type="button" onClick={() => handleAction(ACTIONS.find((action) => action.id === "insights")!)}><Lightbulb size={15} /><span>Find hidden insights</span><ChevronRight size={14} /></button></div></div><div className="rail-callout"><div className="rail-callout-icon"><UploadCloud size={16} /></div><strong>Bring in more context</strong><p>Google Docs, Slides, lecture recordings, and textbook chapters can all live in this workspace.</p><button type="button" onClick={() => setShowSourceComposer(true)}>Add another source <ArrowUpRight size={13} /></button></div></aside>

      {showSourceComposer && <div className="modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) setShowSourceComposer(false); }}><div className="source-composer" role="dialog" aria-modal="true" aria-labelledby="source-composer-title"><div className="composer-heading"><div><p className="eyebrow">Expand the knowledge base</p><h2 id="source-composer-title">Add sources to Atlas</h2><p>Everything you add becomes available to Ask Atlas and the tools below.</p></div><button type="button" className="icon-button" onClick={() => setShowSourceComposer(false)}><X size={17} /></button></div><div className="composer-tabs"><button type="button" className={sourceMode === "files" ? "selected" : ""} onClick={() => setSourceMode("files")}><FileUp size={16} /> Upload files</button><button type="button" className={sourceMode === "link" ? "selected" : ""} onClick={() => setSourceMode("link")}><Globe2 size={16} /> Paste a link</button><button type="button" className={sourceMode === "text" ? "selected" : ""} onClick={() => setSourceMode("text")}><FileText size={16} /> Paste text</button></div>{sourceMode === "files" && <div className="composer-body"><button type="button" className="dropzone" onClick={() => fileInputRef.current?.click()} disabled={sourceBusy}><span className="dropzone-icon"><UploadCloud size={22} /></span><strong>{sourceBusy ? "Adding sources..." : "Choose files from your device"}</strong><span>PDF, DOCX, PPTX, XLSX, TXT, audio, and image files</span></button><input ref={fileInputRef} type="file" multiple accept=".pdf,.docx,.pptx,.xlsx,.csv,.txt,.md,.mp3,.wav,.m4a,.aac,.ogg,.flac,.png,.jpg,.jpeg,.webp" className="visually-hidden" onChange={(event) => void handleFiles(event.target.files)} /><div className="composer-divider"><span>or connect a library</span></div><Link href="/settings/connections" className="google-connect"><span className="google-connect-mark">G</span><span><strong>Connect Google Drive</strong><small>Bring in Google Docs and Slides</small></span><ArrowUpRight size={16} /></Link><p className="composer-footnote">You can also add lecture recordings, textbook chapters, research papers, and course materials as files.</p></div>}{sourceMode === "link" && <form className="composer-body" onSubmit={(event) => void handleUrl(event)}><label className="field-label">Website or YouTube URL<input value={sourceInput} onChange={(event) => setSourceInput(event.target.value)} placeholder="https://..." autoFocus /></label><button type="submit" className="primary-button full-width" disabled={sourceBusy || !sourceInput.trim()}>{sourceBusy ? <><Loader2 size={16} className="spin" /> Adding link</> : <><Plus size={16} /> Add link</>}</button><p className="composer-footnote">Atlas extracts readable web text and YouTube transcripts so answers can point back to the original source.</p></form>}{sourceMode === "text" && <form className="composer-body" onSubmit={(event) => void handleText(event)}><label className="field-label">Title<input value={sourceTextTitle} onChange={(event) => setSourceTextTitle(event.target.value)} placeholder="Lecture notes, research idea, meeting notes..." autoFocus /></label><label className="field-label">Text<textarea value={sourceText} onChange={(event) => setSourceText(event.target.value)} rows={7} placeholder="Paste the material Atlas should understand..." /></label><button type="submit" className="primary-button full-width" disabled={sourceBusy || !sourceText.trim() || !sourceTextTitle.trim()}>{sourceBusy ? <><Loader2 size={16} className="spin" /> Adding text</> : <><Plus size={16} /> Add text</>}</button></form>}</div></div>}

      {selectedSource && <div className="modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) { setSelectedSource(null); setSourcePreview(null); } }}><div className="source-preview-modal" role="dialog" aria-modal="true" aria-labelledby="source-preview-title"><div className="composer-heading"><div><p className="eyebrow">Indexed source</p><h2 id="source-preview-title">{selectedSource.filename}</h2><p>{selectedSource.file_type.toUpperCase()} source text that Atlas can search and cite.</p></div><button type="button" className="icon-button" onClick={() => { setSelectedSource(null); setSourcePreview(null); }}><X size={17} /></button></div>{selectedSource.source_url && <a className="source-preview-link" href={selectedSource.source_url} target="_blank" rel="noreferrer"><SquareArrowOutUpRight size={14} /> Open original source</a>}{previewLoading ? <div className="preview-loading"><Loader2 size={22} className="spin" /><p>Loading the text Atlas indexed...</p></div> : sourcePreview?.chunks.length ? <div className="preview-chunks">{sourcePreview.chunks.map((chunk) => <article className="preview-chunk" key={chunk.id}><span>{chunk.timestamp != null ? `Timestamp ${formatDuration(chunk.timestamp)}` : chunk.page_number ? `Page ${chunk.page_number}` : "Indexed excerpt"}</span><p>{chunk.content}</p></article>)}</div> : <div className="preview-loading"><FileText size={22} /><p>No indexed text is available yet. Check the source status and try again.</p></div>}</div></div>}

      {selectedCitation && <div className="citation-drawer"><div className="citation-drawer-heading"><div><p className="eyebrow">Source reference</p><h3>{selectedCitation.filename || "Atlas source"}</h3></div><button type="button" className="icon-button" onClick={() => setSelectedCitation(null)}><X size={16} /></button></div><div className="citation-meta">{selectedCitation.page_number ? `Page ${selectedCitation.page_number}` : selectedCitation.source_label || "Verified source excerpt"}{selectedCitation.external_url && <a href={selectedCitation.external_url} target="_blank" rel="noreferrer">Open source <SquareArrowOutUpRight size={13} /></a>}</div><blockquote>{selectedCitation.content || selectedCitation.text || "No excerpt was returned for this citation."}</blockquote></div>}
    </div>
  );
}
