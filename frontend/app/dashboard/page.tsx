"use client";

import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import {
  AlertTriangle,
  Bot,
  BookOpen,
  CheckCircle2,
  ChevronRight,
  Database,
  FileText,
  Globe,
  Layers3,
  Loader2,
  Map,
  MessageSquare,
  Network,
  Plus,
  Search,
  Send,
  Sparkles,
  Trash2,
  Upload,
  Video,
  Wand2,
} from "lucide-react";
import Logo from "../../components/brand/logo";
import UserMenu from "../../components/UserMenu";
import { apiClient } from "@/lib/apiClient";
import { supabaseBrowser, getCurrentProfile } from "@/lib/supabaseClient";
import AddSourceModal from "@/app/components/sources/AddSourceModal";
import DeepResearchDrawer from "@/app/components/research/DeepResearchDrawer";
import AudioOverviewPanel from "@/app/components/audio/AudioOverviewPanel";
import { OnboardingTour } from "@/app/dashboard/OnboardingTour";
import { citationLabel } from "@/lib/sources";
import "@/app/components/research/deep-research.css";

type Workspace = {
  id: string;
  name: string;
  created_at?: string;
};

type DocumentSource = {
  id: string;
  workspace_id?: string;
  filename: string;
  file_type: string;
  source_url?: string | null;
  status: "pending" | "processing" | "ready" | "failed";
  error_message?: string | null;
  created_at: string;
};

type ChatSession = {
  id: string;
  workspace_id: string;
  title: string;
  created_at: string;
};

type Message = {
  id: string;
  role: "user" | "assistant";
  content: string;
  citations?: any[];
};

type StudioOutput = {
  id: string;
  workspace_id: string;
  synthesis_node_id: string | null;
  output_type: "mind_map" | "study_guide" | "quiz" | "flashcards";
  title: string;
  status: "pending" | "processing" | "ready" | "failed";
  content: any | null;
  error: string | null;
  error_message?: string | null;
  citations: any[];
  created_at: string;
};

type DashboardView = "ask" | "notes" | "studio" | "canvas" | "agent";

const STUDIO_CARDS = [
  { id: "study_guide", label: "Study Guide", icon: BookOpen, accent: "text-emerald-300 bg-emerald-500/10 border-emerald-500/20" },
  { id: "mind_map", label: "Mind Map", icon: Network, accent: "text-sky-300 bg-sky-500/10 border-sky-500/20" },
  { id: "quiz", label: "Quiz", icon: CheckCircle2, accent: "text-amber-300 bg-amber-500/10 border-amber-500/20" },
  { id: "flashcards", label: "Flashcards", icon: Layers3, accent: "text-violet-300 bg-violet-500/10 border-violet-500/20" },
] as const;

const SUGGESTED_PROMPTS = [
  "What are the strongest claims across these sources?",
  "Where do the sources disagree?",
  "Summarize this notebook with citations.",
  "Turn this material into an action plan.",
];

function normalizeStatus(status?: string): DocumentSource["status"] {
  if (status === "pending" || status === "processing" || status === "failed") return status;
  return "ready";
}

function sourceIcon(type: string) {
  const kind = type.toLowerCase();
  if (kind.includes("youtube")) return Video;
  if (kind.includes("url") || kind.includes("web")) return Globe;
  return FileText;
}

function sourceTone(type: string) {
  const kind = type.toLowerCase();
  if (kind.includes("pdf")) return "text-rose-300 bg-rose-500/10 border-rose-500/20";
  if (kind.includes("youtube")) return "text-red-300 bg-red-500/10 border-red-500/20";
  if (kind.includes("csv") || kind.includes("xlsx")) return "text-emerald-300 bg-emerald-500/10 border-emerald-500/20";
  if (kind.includes("url") || kind.includes("web")) return "text-sky-300 bg-sky-500/10 border-sky-500/20";
  return "text-violet-300 bg-violet-500/10 border-violet-500/20";
}

function outputLabel(type: string) {
  return type.replace(/_/g, " ").replace(/\b\w/g, (m) => m.toUpperCase());
}

function formatDate(value?: string) {
  if (!value) return "";
  return new Date(value).toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

function extractYoutubeTimestamp(content: string): string {
  if (!content) return "";
  const match = content.match(/##\s*\[(\d+:\d+(?::\d+)?)\]/);
  if (match) return match[1];
  const fallback = content.match(/\[(\d+:\d+(?::\d+)?)\]/);
  return fallback ? fallback[1] : "";
}

function parseTimeToSeconds(timeStr: string): number {
  if (!timeStr) return 0;
  const parts = timeStr.split(":").map(Number);
  if (parts.length === 3) return parts[0] * 3600 + parts[1] * 60 + parts[2];
  if (parts.length === 2) return parts[0] * 60 + parts[1];
  return parts[0] || 0;
}

export default function Dashboard() {
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [selectedWorkspace, setSelectedWorkspace] = useState<Workspace | null>(null);
  const [newWorkspaceName, setNewWorkspaceName] = useState("");
  const [sources, setSources] = useState<DocumentSource[]>([]);
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [selectedSessionId, setSelectedSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [chatInput, setChatInput] = useState("");
  const [chatLoading, setChatLoading] = useState(false);
  const [streamingText, setStreamingText] = useState("");
  const [citationsMap, setCitationsMap] = useState<Record<string, any>>({});
  const [selectedCitation, setSelectedCitation] = useState<any | null>(null);
  const [studioOutputs, setStudioOutputs] = useState<StudioOutput[]>([]);
  const [openOutput, setOpenOutput] = useState<StudioOutput | null>(null);
  const [view, setView] = useState<DashboardView>("ask");
  const [token, setToken] = useState("");
  const [userTier, setUserTier] = useState<"Free" | "Pro" | "Team">("Free");
  const [engineStatus, setEngineStatus] = useState<"active" | "inactive" | "loading">("loading");
  const [showAddSource, setShowAddSource] = useState(false);
  const [deepResearchOpen, setDeepResearchOpen] = useState(false);
  const [uiError, setUiError] = useState("");
  const [sourceFilter, setSourceFilter] = useState("");
  const [notes, setNotes] = useState("");
  const [notesSaving, setNotesSaving] = useState(false);
  const [activeScopeNode, setActiveScopeNode] = useState<{ id: string; title: string; count: number } | null>(null);

  const streamingAccumRef = useRef("");
  const citationsMapRef = useRef<Record<string, any>>({});
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const readySources = useMemo(
    () => sources.filter((source) => source.status === "ready"),
    [sources],
  );
  const processingSources = useMemo(
    () => sources.filter((source) => source.status === "pending" || source.status === "processing"),
    [sources],
  );
  const failedSources = useMemo(
    () => sources.filter((source) => source.status === "failed"),
    [sources],
  );
  const filteredSources = useMemo(() => {
    const query = sourceFilter.trim().toLowerCase();
    if (!query) return sources;
    return sources.filter((source) =>
      `${source.filename} ${source.file_type}`.toLowerCase().includes(query),
    );
  }, [sources, sourceFilter]);

  const getErrorMessage = (err: unknown, fallback: string) => {
    if (err instanceof Error && err.message) return err.message;
    return fallback;
  };

  const fetchWorkspaces = useCallback(async () => {
    try {
      const data = await apiClient.get<Workspace[]>("/api/v1/workspaces");
      setWorkspaces(data);
      const savedWorkspaceId = typeof window !== "undefined" ? localStorage.getItem("selectedWorkspaceId") : null;
      const restored = data.find((workspace) => workspace.id === savedWorkspaceId) || data[0] || null;
      setSelectedWorkspace(restored);
      setUiError("");
    } catch (err) {
      setUiError(getErrorMessage(err, "Could not load notebooks."));
    }
  }, []);

  const fetchDocuments = useCallback(async (workspaceId: string) => {
    try {
      const data = await apiClient.get<DocumentSource[]>(`/api/v1/workspaces/${workspaceId}/documents`);
      setSources(
        data.map((source) => ({
          ...source,
          status: normalizeStatus(source.status),
        })),
      );
    } catch (err) {
      setUiError(getErrorMessage(err, "Could not load sources."));
    }
  }, []);

  const fetchStudioOutputs = useCallback(async (workspaceId: string) => {
    try {
      const data = await apiClient.get<StudioOutput[]>(`/api/v1/workspaces/${workspaceId}/studio`);
      setStudioOutputs(data);
      data.forEach((output) => {
        if (output.status === "pending" || output.status === "processing") {
          pollStudioOutput(output.id, workspaceId);
        }
      });
    } catch (err) {
      console.error("Failed to load studio outputs", err);
    }
  }, []);

  const handleCreateSession = useCallback(async (workspaceId: string) => {
    const session = await apiClient.post<ChatSession>(`/api/v1/workspaces/${workspaceId}/sessions`, {
      title: "Grounded Q&A",
    });
    setSessions((prev) => [session, ...prev]);
    setSelectedSessionId(session.id);
  }, []);

  const fetchSessions = useCallback(async (workspaceId: string) => {
    try {
      const data = await apiClient.get<ChatSession[]>(`/api/v1/workspaces/${workspaceId}/sessions`);
      setSessions(data);
      if (data.length === 0) {
        await handleCreateSession(workspaceId);
        return;
      }
      const savedSessionId = typeof window !== "undefined" ? localStorage.getItem(`selectedSessionId:${workspaceId}`) : null;
      setSelectedSessionId(data.find((session) => session.id === savedSessionId)?.id || data[0].id);
    } catch (err) {
      setUiError(getErrorMessage(err, "Could not load chat sessions."));
    }
  }, [handleCreateSession]);

  const fetchSessionDetails = useCallback(async (sessionId: string) => {
    try {
      const data = await apiClient.get<{ messages?: Message[] } & ChatSession>(`/api/v1/sessions/${sessionId}`);
      setMessages(data.messages || []);
    } catch (err) {
      setUiError(getErrorMessage(err, "Could not load chat history."));
    }
  }, []);

  useEffect(() => {
    fetchWorkspaces().catch(console.error);

    const loadSession = async () => {
      const supabase = supabaseBrowser();
      const {
        data: { session },
      } = await supabase.auth.getSession();
      if (session?.access_token) setToken(session.access_token);
    };

    const loadProfile = async () => {
      try {
        const profile = await getCurrentProfile();
        if (profile?.tier) setUserTier(profile.tier);
      } catch (err) {
        console.error("Profile load failed", err);
      }
    };

    const loadEngine = async () => {
      try {
        const data = await apiClient.get<{ providers: { id: string; status: string }[] }>("/api/v1/settings/providers");
        const cloud = data.providers.find((provider) => provider.id === "atlas-cloud");
        setEngineStatus(cloud?.status === "active" ? "active" : "inactive");
      } catch {
        setEngineStatus("inactive");
      }
    };

    loadSession().catch(console.error);
    loadProfile().catch(console.error);
    loadEngine().catch(console.error);
  }, [fetchWorkspaces]);

  useEffect(() => {
    if (!selectedWorkspace) return;
    localStorage.setItem("selectedWorkspaceId", selectedWorkspace.id);
    setMessages([]);
    setSelectedCitation(null);
    setOpenOutput(null);
    setActiveScopeNode(null);
    setNotes(localStorage.getItem(`atlaslm-notes:${selectedWorkspace.id}`) || "");
    fetchDocuments(selectedWorkspace.id);
    fetchSessions(selectedWorkspace.id);
    fetchStudioOutputs(selectedWorkspace.id);
  }, [fetchDocuments, fetchSessions, fetchStudioOutputs, selectedWorkspace]);

  useEffect(() => {
    if (!selectedWorkspace || !selectedSessionId) return;
    localStorage.setItem(`selectedSessionId:${selectedWorkspace.id}`, selectedSessionId);
    fetchSessionDetails(selectedSessionId);
  }, [fetchSessionDetails, selectedSessionId, selectedWorkspace]);

  useEffect(() => {
    if (!selectedWorkspace) return;
    localStorage.setItem(`atlaslm-notes:${selectedWorkspace.id}`, notes);
  }, [notes, selectedWorkspace]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, streamingText, view]);

  useEffect(() => {
    if (!selectedWorkspace || processingSources.length === 0) return;
    const interval = setInterval(() => fetchDocuments(selectedWorkspace.id), 3000);
    return () => clearInterval(interval);
  }, [fetchDocuments, processingSources.length, selectedWorkspace]);

  const handleCreateWorkspace = async (event: React.FormEvent) => {
    event.preventDefault();
    const name = newWorkspaceName.trim();
    if (!name) return;
    try {
      const workspace = await apiClient.post<Workspace>("/api/v1/workspaces", { name });
      setWorkspaces((prev) => [workspace, ...prev]);
      setSelectedWorkspace(workspace);
      setNewWorkspaceName("");
      setUiError("");
    } catch (err) {
      setUiError(getErrorMessage(err, "Could not create notebook."));
    }
  };

  const handleDeleteDocument = async (documentId: string) => {
    try {
      await apiClient.del(`/api/v1/documents/${documentId}`);
      setSources((prev) => prev.filter((source) => source.id !== documentId));
    } catch (err) {
      setUiError(getErrorMessage(err, "Could not delete source."));
    }
  };

  const handleSaveNotesAsSource = async () => {
    if (!selectedWorkspace || !notes.trim()) return;
    setNotesSaving(true);
    try {
      await apiClient.post(`/api/v1/workspaces/${selectedWorkspace.id}/documents/text`, {
        title: `Notebook notes - ${new Date().toLocaleDateString()}`,
        content: notes.trim(),
      });
      await fetchDocuments(selectedWorkspace.id);
      setUiError("");
    } catch (err) {
      setUiError(getErrorMessage(err, "Could not add notes as a source."));
    } finally {
      setNotesSaving(false);
    }
  };

  const handleSendChatMessage = async (event?: React.FormEvent, promptOverride?: string) => {
    event?.preventDefault();
    const query = (promptOverride || chatInput).trim();
    if (!query || !selectedSessionId || chatLoading) return;

    setChatInput("");
    setChatLoading(true);
    setStreamingText("");
    streamingAccumRef.current = "";
    citationsMapRef.current = {};

    setMessages((prev) => [
      ...prev,
      {
        id: crypto.randomUUID(),
        role: "user",
        content: query,
      },
    ]);

    try {
      const response = await apiClient.stream(`/api/v1/sessions/${selectedSessionId}/chat/stream`, {
        content: query,
        synthesis_node_id: activeScopeNode?.id || null,
      });

      const reader = response.body?.getReader();
      if (!reader) throw new Error("No response stream.");
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";

        for (const line of lines) {
          const cleanLine = line.trim();
          if (!cleanLine.startsWith("data: ")) continue;
          const dataStr = cleanLine.slice(6).trim();
          if (dataStr === "[DONE]") break;
          try {
            const payload = JSON.parse(dataStr);
            if (payload.type === "metadata") {
              citationsMapRef.current = payload.sources || {};
              setCitationsMap(payload.sources || {});
            } else if (payload.type === "chunk") {
              streamingAccumRef.current += payload.content;
              setStreamingText(streamingAccumRef.current);
            } else if (payload.error) {
              throw new Error(payload.error);
            }
          } catch (err) {
            console.error("Stream parse failed", err);
          }
        }
      }

      setMessages((prev) => [
        ...prev,
        {
          id: crypto.randomUUID(),
          role: "assistant",
          content: streamingAccumRef.current,
          citations: Object.values(citationsMapRef.current),
        },
      ]);
      setStreamingText("");
      setUiError("");
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        {
          id: crypto.randomUUID(),
          role: "assistant",
          content: "AtlasLM could not complete that request. Check the source set and try again.",
        },
      ]);
      setUiError(getErrorMessage(err, "Chat request failed."));
    } finally {
      setChatLoading(false);
    }
  };

  const pollStudioOutput = (outputId: string, workspaceId?: string) => {
    const id = workspaceId || selectedWorkspace?.id;
    if (!id) return;
    const interval = setInterval(async () => {
      try {
        const output = await apiClient.get<StudioOutput>(`/api/v1/workspaces/${id}/studio/${outputId}`);
        setStudioOutputs((prev) => prev.map((item) => (item.id === output.id ? output : item)));
        setOpenOutput((current) => (current?.id === output.id ? output : current));
        if (output.status === "ready" || output.status === "failed") clearInterval(interval);
      } catch (err) {
        console.error("Studio polling failed", err);
        clearInterval(interval);
      }
    }, 1600);
  };

  const generateStudioOutput = async (outputType: StudioOutput["output_type"]) => {
    if (!selectedWorkspace) return;
    if (readySources.length === 0) {
      setUiError("Add a source first, then AtlasLM can generate cited outputs.");
      setShowAddSource(true);
      return;
    }

    try {
      const response = await apiClient.postRaw(`/api/v1/workspaces/${selectedWorkspace.id}/studio`, {
        output_type: outputType,
        synthesis_node_id: activeScopeNode?.id || null,
      });
      const body = await response.json();
      if (!response.ok) {
        setUiError(body.detail || "Could not generate this output.");
        return;
      }
      setStudioOutputs((prev) => [body, ...prev]);
      setOpenOutput(body);
      setView("studio");
      pollStudioOutput(body.id, selectedWorkspace.id);
      setUiError("");
    } catch (err) {
      setUiError(getErrorMessage(err, "Could not generate this output."));
    }
  };

  const handleDeleteStudioOutput = async (outputId: string) => {
    if (!selectedWorkspace) return;
    try {
      await apiClient.del(`/api/v1/workspaces/${selectedWorkspace.id}/studio/${outputId}`);
      setStudioOutputs((prev) => prev.filter((output) => output.id !== outputId));
      setOpenOutput((current) => (current?.id === outputId ? null : current));
    } catch (err) {
      setUiError(getErrorMessage(err, "Could not delete Studio output."));
    }
  };

  const renderMessageContent = (content: string, msgCitations?: any[]) => {
    const parts = content.split(/(\[source_\d+\])/g);
    return parts.map((part, idx) => {
      const match = part.match(/\[source_(\d+)\]/);
      if (!match) return <span key={idx}>{part}</span>;
      const tag = `source_${match[1]}`;
      const sourceDetails =
        (msgCitations && msgCitations.find((citation: any) => citation.tag === tag)) ||
        citationsMap[tag] ||
        null;
      const isYoutube =
        sourceDetails?.file_type === "youtube" ||
        (sourceDetails?.filename && sourceDetails.filename.endsWith(" (YouTube)"));
      let chipText = match[1];
      if (isYoutube && sourceDetails) {
        const ts = extractYoutubeTimestamp(sourceDetails.content || sourceDetails.text || "");
        if (ts) chipText = `@ ${ts}`;
      }

      return (
        <button
          key={idx}
          type="button"
          onClick={() => sourceDetails && setSelectedCitation(sourceDetails)}
          className="mx-1 inline-flex h-5 items-center rounded border border-emerald-400/25 bg-emerald-400/10 px-1.5 text-[10px] font-semibold text-emerald-200 hover:bg-emerald-400/20"
        >
          {chipText}
        </button>
      );
    });
  };

  const renderOutputPreview = (output: StudioOutput | null) => {
    if (!output) {
      return (
        <div className="flex h-full min-h-[280px] items-center justify-center rounded border border-dashed border-zinc-800 bg-zinc-950/40 text-sm text-zinc-500">
          Select or generate an output.
        </div>
      );
    }
    if (output.status === "pending" || output.status === "processing") {
      return (
        <div className="flex h-full min-h-[280px] flex-col items-center justify-center gap-3 rounded border border-zinc-800 bg-zinc-950/60">
          <Loader2 className="h-6 w-6 animate-spin text-emerald-300" />
          <span className="text-sm text-zinc-300">Generating {outputLabel(output.output_type)}</span>
        </div>
      );
    }
    if (output.status === "failed") {
      return (
        <div className="rounded border border-red-500/20 bg-red-500/5 p-4 text-sm text-red-200">
          {output.error || output.error_message || "Generation failed."}
        </div>
      );
    }

    const content = output.content || {};
    if (output.output_type === "mind_map") {
      const branches = content.branches || [];
      return (
        <div className="space-y-4">
          <div className="rounded border border-sky-400/20 bg-sky-400/10 p-4">
            <div className="text-xs uppercase tracking-wide text-sky-200">Root</div>
            <div className="mt-1 text-lg font-semibold text-white">{content.root || output.title}</div>
          </div>
          <div className="grid gap-3 md:grid-cols-2">
            {branches.map((branch: any, index: number) => (
              <div key={index} className="rounded border border-zinc-800 bg-zinc-950/60 p-4">
                <div className="font-semibold text-zinc-100">{branch.label}</div>
                <ul className="mt-3 space-y-2 text-sm text-zinc-400">
                  {(branch.children || []).map((child: string, childIndex: number) => (
                    <li key={childIndex} className="flex gap-2">
                      <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-sky-300" />
                      <span>{child}</span>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </div>
      );
    }

    if (output.output_type === "study_guide") {
      return (
        <div className="space-y-3">
          {(content.sections || []).map((section: any, index: number) => (
            <div key={index} className="rounded border border-zinc-800 bg-zinc-950/60 p-4">
              <h3 className="font-semibold text-white">{section.heading}</h3>
              <p className="mt-2 text-sm leading-6 text-zinc-400">{section.summary}</p>
              <ul className="mt-3 space-y-2 text-sm text-zinc-300">
                {(section.key_points || []).slice(0, 5).map((point: string, pointIndex: number) => (
                  <li key={pointIndex} className="flex gap-2">
                    <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-emerald-300" />
                    <span>{point}</span>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      );
    }

    if (output.output_type === "quiz") {
      return (
        <div className="space-y-3">
          {(content.questions || []).map((question: any, index: number) => (
            <div key={index} className="rounded border border-zinc-800 bg-zinc-950/60 p-4">
              <div className="font-semibold text-white">{index + 1}. {question.question}</div>
              <div className="mt-3 grid gap-2 md:grid-cols-2">
                {(question.choices || []).map((choice: string, choiceIndex: number) => (
                  <div
                    key={choiceIndex}
                    className={`rounded border px-3 py-2 text-sm ${
                      choiceIndex === question.answer_index
                        ? "border-emerald-400/25 bg-emerald-400/10 text-emerald-100"
                        : "border-zinc-800 bg-zinc-900/40 text-zinc-400"
                    }`}
                  >
                    {choice}
                  </div>
                ))}
              </div>
              {question.explanation && <p className="mt-3 text-sm text-zinc-500">{question.explanation}</p>}
            </div>
          ))}
        </div>
      );
    }

    if (output.output_type === "flashcards") {
      return (
        <div className="grid gap-3 md:grid-cols-2">
          {(content.cards || []).map((card: any, index: number) => (
            <div key={index} className="rounded border border-zinc-800 bg-zinc-950/60 p-4">
              <div className="text-xs uppercase tracking-wide text-violet-200">Prompt</div>
              <div className="mt-1 font-semibold text-white">{card.front}</div>
              <div className="mt-4 text-xs uppercase tracking-wide text-emerald-200">Answer</div>
              <p className="mt-1 text-sm leading-6 text-zinc-400">{card.back}</p>
            </div>
          ))}
        </div>
      );
    }

    return <pre className="overflow-auto rounded border border-zinc-800 bg-zinc-950 p-4 text-xs text-zinc-300">{JSON.stringify(content, null, 2)}</pre>;
  };

  const renderAskEmptyState = () => {
    if (readySources.length === 0) {
      return (
        <div className="mx-auto grid max-w-4xl gap-5 pt-8">
          <div className="rounded border border-zinc-800 bg-zinc-950/70 p-6">
            <div className="flex items-start gap-4">
              <span className="flex h-12 w-12 shrink-0 items-center justify-center rounded border border-emerald-400/20 bg-emerald-400/10 text-emerald-200">
                <Sparkles className="h-6 w-6" />
              </span>
              <div className="min-w-0">
                <p className="text-xs font-semibold uppercase tracking-wide text-emerald-200">Personal source expert</p>
                <h1 className="mt-2 text-2xl font-semibold text-white">Add your material, then ask AtlasLM.</h1>
                <p className="mt-3 max-w-2xl text-sm leading-6 text-zinc-400">
                  This notebook answers from your PDFs, notes, websites, and videos. Once a source is indexed, every answer can point back to the material it used.
                </p>
              </div>
            </div>

            <div className="mt-6 grid gap-3 sm:grid-cols-3">
              <button
                type="button"
                onClick={() => setShowAddSource(true)}
                disabled={!selectedWorkspace}
                className="rounded border border-zinc-700 bg-zinc-100 p-4 text-left text-zinc-950 hover:bg-white disabled:opacity-40"
              >
                <Upload className="h-5 w-5" />
                <div className="mt-3 text-sm font-semibold">Add files or links</div>
                <p className="mt-1 text-xs leading-5 text-zinc-600">Upload PDFs, paste URLs, or bring in video transcripts.</p>
              </button>
              <button
                type="button"
                onClick={() => setDeepResearchOpen(true)}
                disabled={!selectedWorkspace}
                className="rounded border border-sky-400/20 bg-sky-400/10 p-4 text-left text-sky-100 hover:bg-sky-400/15 disabled:opacity-40"
              >
                <Search className="h-5 w-5" />
                <div className="mt-3 text-sm font-semibold text-white">Discover sources</div>
                <p className="mt-1 text-xs leading-5 text-sky-100/70">Use the agent to find relevant sources and ingest the useful ones.</p>
              </button>
              <button
                type="button"
                onClick={() => setView("notes")}
                disabled={!selectedWorkspace}
                className="rounded border border-violet-400/20 bg-violet-400/10 p-4 text-left text-violet-100 hover:bg-violet-400/15 disabled:opacity-40"
              >
                <BookOpen className="h-5 w-5" />
                <div className="mt-3 text-sm font-semibold text-white">Start with notes</div>
                <p className="mt-1 text-xs leading-5 text-violet-100/70">Draft notes here and add them as a grounded source.</p>
              </button>
            </div>
          </div>

          <div className="rounded border border-zinc-800 bg-zinc-950/60 p-5">
            <h2 className="text-sm font-semibold text-white">What unlocks after indexing</h2>
            <div className="mt-4 grid gap-4 sm:grid-cols-2">
              {[
                ["Grounded Q&A", "Ask questions with inline source citations."],
                ["Studio outputs", "Generate study guides, quizzes, flashcards, and maps."],
                ["Audio overview", "Create a spoken summary from selected sources."],
                ["Living notebook", "Keep notes and generated artifacts next to the source set."],
              ].map(([title, body]) => (
                <div key={title} className="flex gap-3">
                  <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-emerald-300" />
                  <div>
                    <div className="text-sm font-medium text-zinc-100">{title}</div>
                    <div className="mt-1 text-xs leading-5 text-zinc-500">{body}</div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      );
    }

    return (
      <div className="mx-auto flex max-w-3xl flex-col gap-5 pt-12">
        <div className="rounded border border-zinc-800 bg-zinc-950/70 p-5">
          <div className="flex items-center gap-3">
            <span className="flex h-10 w-10 items-center justify-center rounded border border-emerald-400/20 bg-emerald-400/10 text-emerald-200">
              <Sparkles className="h-5 w-5" />
            </span>
            <div>
              <h1 className="text-xl font-semibold text-white">Ask this notebook</h1>
              <p className="mt-1 text-sm text-zinc-500">Answers stay grounded in {readySources.length} ready source{readySources.length === 1 ? "" : "s"}.</p>
            </div>
          </div>
        </div>

        <div className="grid gap-2 md:grid-cols-2">
          {SUGGESTED_PROMPTS.map((prompt) => (
            <button
              key={prompt}
              type="button"
              onClick={() => handleSendChatMessage(undefined, prompt)}
              disabled={chatLoading}
              className="rounded border border-zinc-800 bg-zinc-950/70 p-4 text-left text-sm text-zinc-300 hover:border-zinc-700 hover:bg-zinc-900 disabled:cursor-not-allowed disabled:opacity-40"
            >
              {prompt}
            </button>
          ))}
        </div>
      </div>
    );
  };

  const renderSourceMap = () => {
    if (!selectedWorkspace) {
      return <div className="flex h-full items-center justify-center text-sm text-zinc-500">Select a notebook</div>;
    }

    const visibleSources = sources.slice(0, 7);
    const visibleOutputs = studioOutputs.slice(0, 5);
    const hasSources = sources.length > 0;

    return (
      <section className="flex min-h-0 flex-1 flex-col overflow-hidden">
        <div className="flex shrink-0 items-center justify-between border-b border-zinc-900 px-5 py-4">
          <div>
            <p className="text-xs font-semibold uppercase tracking-wide text-zinc-500">Source map</p>
            <h1 className="mt-1 text-xl font-semibold text-white">{selectedWorkspace.name}</h1>
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => setShowAddSource(true)}
              className="flex h-9 items-center gap-2 rounded bg-zinc-100 px-3 text-sm font-semibold text-zinc-950 hover:bg-white"
            >
              <Upload className="h-4 w-4" />
              Add source
            </button>
            <button
              type="button"
              onClick={() => setView("ask")}
              className="flex h-9 items-center gap-2 rounded border border-zinc-800 bg-zinc-950 px-3 text-sm text-zinc-200 hover:bg-zinc-900"
            >
              <MessageSquare className="h-4 w-4" />
              Ask
            </button>
          </div>
        </div>

        <div className="grid min-h-0 flex-1 gap-4 p-5 lg:grid-cols-[minmax(0,1fr)_290px]">
          <div
            className="relative min-h-[520px] overflow-hidden rounded border border-zinc-800 bg-[#08090b]"
            style={{
              backgroundImage: "radial-gradient(circle at 1px 1px, rgba(113,113,122,0.22) 1px, transparent 0)",
              backgroundSize: "28px 28px",
            }}
          >
            {!hasSources ? (
              <div className="flex h-full min-h-[520px] flex-col items-center justify-center px-6 text-center">
                <span className="flex h-14 w-14 items-center justify-center rounded border border-emerald-400/20 bg-emerald-400/10 text-emerald-200">
                  <Network className="h-7 w-7" />
                </span>
                <h2 className="mt-5 text-2xl font-semibold text-white">Your map starts with sources.</h2>
                <p className="mt-3 max-w-md text-sm leading-6 text-zinc-400">
                  Add at least one document, note, URL, or video. AtlasLM will turn it into a navigable research graph and cited assistant context.
                </p>
                <div className="mt-6 flex flex-wrap justify-center gap-3">
                  <button
                    type="button"
                    onClick={() => setShowAddSource(true)}
                    className="flex h-10 items-center gap-2 rounded bg-zinc-100 px-4 text-sm font-semibold text-zinc-950 hover:bg-white"
                  >
                    <Upload className="h-4 w-4" />
                    Add source
                  </button>
                  <button
                    type="button"
                    onClick={() => setDeepResearchOpen(true)}
                    className="flex h-10 items-center gap-2 rounded border border-sky-400/20 bg-sky-400/10 px-4 text-sm font-semibold text-sky-100 hover:bg-sky-400/15"
                  >
                    <Search className="h-4 w-4" />
                    Discover
                  </button>
                </div>
              </div>
            ) : (
              <div className="grid h-full min-h-[520px] grid-cols-[minmax(0,1fr)_180px_minmax(0,1fr)] gap-5 p-6 max-lg:grid-cols-1">
                <div className="flex flex-col justify-center gap-3">
                  <div className="mb-1 text-xs font-semibold uppercase tracking-wide text-zinc-500">Sources</div>
                  {visibleSources.map((source) => {
                    const Icon = sourceIcon(source.file_type);
                    const isBusy = source.status === "pending" || source.status === "processing";
                    return (
                      <div key={source.id} className="rounded border border-zinc-800 bg-zinc-950/90 p-3 shadow-lg shadow-black/20">
                        <div className="flex items-center gap-3">
                          <span className={`flex h-9 w-9 shrink-0 items-center justify-center rounded border ${sourceTone(source.file_type)}`}>
                            {isBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Icon className="h-4 w-4" />}
                          </span>
                          <div className="min-w-0">
                            <div className="truncate text-sm font-medium text-white" title={source.filename}>{source.filename}</div>
                            <div className="mt-1 text-[11px] uppercase tracking-wide text-zinc-500">{source.file_type} - {source.status}</div>
                          </div>
                        </div>
                      </div>
                    );
                  })}
                  {sources.length > visibleSources.length && (
                    <div className="rounded border border-dashed border-zinc-800 bg-zinc-950/50 p-3 text-xs text-zinc-500">
                      +{sources.length - visibleSources.length} more sources in this notebook
                    </div>
                  )}
                </div>

                <div className="flex items-center justify-center">
                  <div className="w-full rounded border border-emerald-400/25 bg-emerald-400/10 p-5 text-center">
                    <Sparkles className="mx-auto h-7 w-7 text-emerald-200" />
                    <div className="mt-3 text-base font-semibold text-white">AtlasLM Notebook</div>
                    <div className="mt-2 text-xs leading-5 text-emerald-100/70">
                      {readySources.length} ready / {processingSources.length} indexing / {failedSources.length} failed
                    </div>
                    <button
                      type="button"
                      onClick={() => setView("ask")}
                      className="mt-4 h-9 rounded bg-emerald-300 px-3 text-sm font-semibold text-zinc-950 hover:bg-emerald-200"
                    >
                      Ask all sources
                    </button>
                  </div>
                </div>

                <div className="flex flex-col justify-center gap-3">
                  <div className="mb-1 text-xs font-semibold uppercase tracking-wide text-zinc-500">Outputs</div>
                  {visibleOutputs.length > 0 ? (
                    visibleOutputs.map((output) => (
                      <button
                        key={output.id}
                        type="button"
                        onClick={() => {
                          setOpenOutput(output);
                          setView("studio");
                        }}
                        className="rounded border border-zinc-800 bg-zinc-950/90 p-3 text-left hover:bg-zinc-900"
                      >
                        <div className="flex items-center justify-between gap-3">
                          <div className="min-w-0">
                            <div className="truncate text-sm font-medium text-white">{output.title}</div>
                            <div className="mt-1 text-[11px] uppercase tracking-wide text-zinc-500">{outputLabel(output.output_type)} - {output.status}</div>
                          </div>
                          {output.status === "ready" ? (
                            <CheckCircle2 className="h-4 w-4 shrink-0 text-emerald-300" />
                          ) : output.status === "failed" ? (
                            <AlertTriangle className="h-4 w-4 shrink-0 text-red-300" />
                          ) : (
                            <Loader2 className="h-4 w-4 shrink-0 animate-spin text-amber-300" />
                          )}
                        </div>
                      </button>
                    ))
                  ) : (
                    STUDIO_CARDS.slice(0, 3).map((card) => {
                      const Icon = card.icon;
                      return (
                        <button
                          key={card.id}
                          type="button"
                          onClick={() => generateStudioOutput(card.id)}
                          className="rounded border border-zinc-800 bg-zinc-950/90 p-3 text-left hover:bg-zinc-900"
                        >
                          <Icon className="h-4 w-4 text-zinc-300" />
                          <div className="mt-2 text-sm font-medium text-white">Generate {card.label}</div>
                        </button>
                      );
                    })
                  )}
                </div>
              </div>
            )}
          </div>

          <div className="min-h-0 overflow-y-auto rounded border border-zinc-800 bg-zinc-950/60 p-4">
            <h2 className="text-sm font-semibold text-white">Notebook workflow</h2>
            <div className="mt-4 space-y-3">
              {[
                ["Add", "Bring in PDFs, URLs, YouTube, or text notes.", sources.length > 0],
                ["Index", "AtlasLM chunks and embeds the material for retrieval.", readySources.length > 0],
                ["Ask", "Chat answers are constrained to your sources.", messages.length > 0],
                ["Generate", "Create study guides, quizzes, flashcards, and maps.", studioOutputs.length > 0],
              ].map(([title, body, done]) => (
                <div key={String(title)} className="flex gap-3 rounded border border-zinc-800 bg-zinc-950/80 p-3">
                  {done ? (
                    <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-emerald-300" />
                  ) : (
                    <span className="mt-1 h-3 w-3 shrink-0 rounded-full border border-zinc-600" />
                  )}
                  <div>
                    <div className="text-sm font-medium text-zinc-100">{title}</div>
                    <div className="mt-1 text-xs leading-5 text-zinc-500">{body}</div>
                  </div>
                </div>
              ))}
            </div>

            <div className="mt-4 grid grid-cols-3 gap-2">
              <div className="rounded border border-zinc-800 bg-zinc-950 p-2 text-center">
                <div className="text-lg font-semibold text-white">{readySources.length}</div>
                <div className="text-[10px] uppercase tracking-wide text-zinc-500">Ready</div>
              </div>
              <div className="rounded border border-zinc-800 bg-zinc-950 p-2 text-center">
                <div className="text-lg font-semibold text-white">{processingSources.length}</div>
                <div className="text-[10px] uppercase tracking-wide text-zinc-500">Indexing</div>
              </div>
              <div className="rounded border border-zinc-800 bg-zinc-950 p-2 text-center">
                <div className="text-lg font-semibold text-white">{studioOutputs.length}</div>
                <div className="text-[10px] uppercase tracking-wide text-zinc-500">Outputs</div>
              </div>
            </div>
          </div>
        </div>
      </section>
    );
  };

  const viewButton = (id: DashboardView, label: string, Icon: typeof MessageSquare) => (
    <button
      type="button"
      onClick={() => setView(id)}
      className={`flex h-9 items-center gap-2 rounded px-3 text-sm font-medium transition ${
        view === id
          ? "bg-zinc-100 text-zinc-950"
          : "text-zinc-400 hover:bg-zinc-900 hover:text-zinc-100"
      }`}
    >
      <Icon className="h-4 w-4" />
      {label}
    </button>
  );

  return (
    <div className="flex h-screen min-h-[720px] flex-col overflow-hidden bg-[#08090b] text-zinc-100">
      <header className="flex h-16 shrink-0 items-center justify-between border-b border-zinc-900 bg-[#0b0c0f] px-5">
        <div className="flex items-center gap-4">
          <Link href="/" className="flex items-center gap-3">
            <Logo size={32} showText={false} />
            <span className="text-sm font-semibold tracking-tight text-white">AtlasLM</span>
          </Link>
          <div className="hidden h-6 w-px bg-zinc-800 md:block" />
          <div className="hidden items-center gap-2 text-xs text-zinc-500 md:flex">
            <Database className="h-3.5 w-3.5" />
            <span>{selectedWorkspace?.name || "No notebook selected"}</span>
          </div>
        </div>

        <div className="flex items-center gap-3">
          <div className="hidden items-center gap-2 rounded border border-zinc-800 bg-zinc-950 px-3 py-2 text-xs text-zinc-300 sm:flex">
            <span className={`h-2 w-2 rounded-full ${engineStatus === "active" ? "bg-emerald-400" : engineStatus === "loading" ? "bg-amber-300" : "bg-zinc-600"}`} />
            <span>{engineStatus === "active" ? "AtlasLM Engine" : engineStatus === "loading" ? "Checking engine" : "Local Engine"}</span>
          </div>
          <button
            type="button"
            onClick={() => setDeepResearchOpen(true)}
            className="hidden h-9 items-center gap-2 rounded border border-emerald-400/20 bg-emerald-400/10 px-3 text-sm font-medium text-emerald-100 hover:bg-emerald-400/15 md:flex"
          >
            <Sparkles className="h-4 w-4" />
            Discover
          </button>
          <UserMenu />
        </div>
      </header>

      <div className="grid min-h-0 flex-1 grid-cols-[300px_minmax(0,1fr)_360px] max-xl:grid-cols-[280px_minmax(0,1fr)]">
        <aside className="flex min-h-0 flex-col border-r border-zinc-900 bg-[#0b0c0f]">
          <div className="border-b border-zinc-900 p-4">
            <form onSubmit={handleCreateWorkspace} className="flex gap-2">
              <input
                value={newWorkspaceName}
                onChange={(event) => setNewWorkspaceName(event.target.value)}
                placeholder="New notebook"
                className="h-10 min-w-0 flex-1 rounded border border-zinc-800 bg-zinc-950 px-3 text-sm text-zinc-100 outline-none placeholder:text-zinc-600 focus:border-zinc-600"
              />
              <button
                type="submit"
                className="flex h-10 w-10 items-center justify-center rounded bg-zinc-100 text-zinc-950 hover:bg-white"
                title="Create notebook"
              >
                <Plus className="h-4 w-4" />
              </button>
            </form>
          </div>

          <div className="border-b border-zinc-900 p-4">
            <div className="mb-3 flex items-center justify-between">
              <span className="text-[11px] font-semibold uppercase tracking-wide text-zinc-500">Notebooks</span>
              <span className="rounded bg-zinc-900 px-2 py-0.5 text-[10px] text-zinc-500">{workspaces.length}</span>
            </div>
            <div className="max-h-44 space-y-1 overflow-y-auto pr-1">
              {workspaces.map((workspace) => (
                <button
                  key={workspace.id}
                  type="button"
                  onClick={() => setSelectedWorkspace(workspace)}
                  className={`flex w-full items-center justify-between rounded border px-3 py-2 text-left text-sm transition ${
                    selectedWorkspace?.id === workspace.id
                      ? "border-zinc-700 bg-zinc-900 text-white"
                      : "border-transparent text-zinc-400 hover:bg-zinc-900/70 hover:text-zinc-100"
                  }`}
                >
                  <span className="truncate">{workspace.name}</span>
                  <ChevronRight className="h-4 w-4 shrink-0 text-zinc-600" />
                </button>
              ))}
            </div>
          </div>

          <div className="flex min-h-0 flex-1 flex-col p-4">
            <div className="mb-3 flex items-center justify-between">
              <span className="text-[11px] font-semibold uppercase tracking-wide text-zinc-500">Sources</span>
              <button
                type="button"
                onClick={() => setShowAddSource(true)}
                disabled={!selectedWorkspace}
                className="flex h-8 items-center gap-2 rounded bg-zinc-100 px-2.5 text-xs font-semibold text-zinc-950 hover:bg-white disabled:opacity-40"
              >
                <Upload className="h-3.5 w-3.5" />
                Add
              </button>
            </div>

            <div className="relative mb-3">
              <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-zinc-600" />
              <input
                value={sourceFilter}
                onChange={(event) => setSourceFilter(event.target.value)}
                placeholder="Search sources"
                className="h-9 w-full rounded border border-zinc-800 bg-zinc-950 pl-9 pr-3 text-sm text-zinc-100 outline-none placeholder:text-zinc-600 focus:border-zinc-600"
              />
            </div>

            <div className="mb-3 grid grid-cols-3 gap-2">
              <div className="rounded border border-zinc-800 bg-zinc-950 p-2">
                <div className="text-base font-semibold text-white">{readySources.length}</div>
                <div className="text-[10px] uppercase tracking-wide text-zinc-500">Ready</div>
              </div>
              <div className="rounded border border-zinc-800 bg-zinc-950 p-2">
                <div className="text-base font-semibold text-white">{processingSources.length}</div>
                <div className="text-[10px] uppercase tracking-wide text-zinc-500">Indexing</div>
              </div>
              <div className="rounded border border-zinc-800 bg-zinc-950 p-2">
                <div className="text-base font-semibold text-white">{failedSources.length}</div>
                <div className="text-[10px] uppercase tracking-wide text-zinc-500">Failed</div>
              </div>
            </div>

            <div className="min-h-0 flex-1 space-y-2 overflow-y-auto pr-1">
              {filteredSources.length === 0 ? (
                <div className="rounded border border-dashed border-zinc-800 bg-zinc-950/50 p-4 text-sm text-zinc-500">
                  <FileText className="h-5 w-5 text-zinc-600" />
                  <div className="mt-3 font-medium text-zinc-300">No sources yet</div>
                  <p className="mt-1 text-xs leading-5">Add a document, URL, YouTube video, or note to wake up this notebook.</p>
                  <button
                    type="button"
                    onClick={() => setShowAddSource(true)}
                    disabled={!selectedWorkspace}
                    className="mt-4 flex h-8 items-center gap-2 rounded bg-zinc-100 px-3 text-xs font-semibold text-zinc-950 hover:bg-white disabled:opacity-40"
                  >
                    <Upload className="h-3.5 w-3.5" />
                    Add source
                  </button>
                </div>
              ) : (
                filteredSources.map((source) => {
                  const Icon = sourceIcon(source.file_type);
                  const isBusy = source.status === "pending" || source.status === "processing";
                  return (
                    <div key={source.id} className="group rounded border border-zinc-850 bg-zinc-950/70 p-3">
                      <div className="flex items-start gap-3">
                        <span className={`flex h-9 w-9 shrink-0 items-center justify-center rounded border ${sourceTone(source.file_type)}`}>
                          {isBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Icon className="h-4 w-4" />}
                        </span>
                        <div className="min-w-0 flex-1">
                          <div className="truncate text-sm font-medium text-zinc-100" title={source.filename}>{source.filename}</div>
                          <div className="mt-1 flex items-center gap-2 text-[11px] text-zinc-500">
                            <span className="uppercase">{source.file_type}</span>
                            <span>{source.status}</span>
                            <span>{formatDate(source.created_at)}</span>
                          </div>
                          {source.error_message && <div className="mt-1 text-[11px] text-red-300">{source.error_message}</div>}
                        </div>
                        <button
                          type="button"
                          onClick={() => handleDeleteDocument(source.id)}
                          className="flex h-7 w-7 shrink-0 items-center justify-center rounded text-zinc-600 opacity-0 hover:bg-red-500/10 hover:text-red-300 group-hover:opacity-100"
                          title="Delete source"
                        >
                          <Trash2 className="h-4 w-4" />
                        </button>
                      </div>
                    </div>
                  );
                })
              )}
            </div>
          </div>
        </aside>

        <main className="flex min-h-0 flex-col bg-[#090a0d]">
          <div className="flex shrink-0 items-center justify-between border-b border-zinc-900 px-5 py-3">
            <div className="flex flex-wrap items-center gap-2">
              {viewButton("ask", "Ask", MessageSquare)}
              {viewButton("notes", "Notes", BookOpen)}
              {viewButton("studio", "Studio", Wand2)}
              {viewButton("canvas", "Map", Map)}
              {viewButton("agent", "Agent", Bot)}
            </div>
            <div className="flex items-center gap-2 text-xs text-zinc-500">
              <span className="rounded border border-zinc-800 bg-zinc-950 px-2 py-1">{userTier}</span>
              <span>{readySources.length} ready sources</span>
            </div>
          </div>

          {uiError && (
            <div className="mx-5 mt-4 flex items-center gap-2 rounded border border-red-500/20 bg-red-500/10 px-3 py-2 text-sm text-red-100">
              <AlertTriangle className="h-4 w-4 shrink-0" />
              <span className="min-w-0 flex-1">{uiError}</span>
              <button type="button" onClick={() => setUiError("")} className="text-red-200 hover:text-white">Dismiss</button>
            </div>
          )}

          {view === "ask" && (
            <section className="flex min-h-0 flex-1 flex-col">
              <div className="min-h-0 flex-1 overflow-y-auto px-5 py-5">
                {activeScopeNode && (
                  <div className="mb-4 inline-flex items-center gap-2 rounded border border-violet-400/20 bg-violet-400/10 px-3 py-1.5 text-xs text-violet-100">
                    <span>{activeScopeNode.title}</span>
                    <span className="text-violet-300">{activeScopeNode.count} sources</span>
                    <button type="button" onClick={() => setActiveScopeNode(null)} className="text-violet-200 hover:text-white">Clear</button>
                  </div>
                )}

                {messages.length === 0 && !streamingText ? (
                  renderAskEmptyState()
                ) : (
                  <div className="mx-auto flex max-w-4xl flex-col gap-5">
                    {messages.map((message) => {
                      const isUser = message.role === "user";
                      return (
                        <div key={message.id} className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
                          <div className={`max-w-[82%] rounded border p-4 text-sm leading-6 ${
                            isUser
                              ? "border-zinc-700 bg-zinc-100 text-zinc-950"
                              : "border-zinc-800 bg-zinc-950/80 text-zinc-200"
                          }`}>
                            {isUser ? message.content : renderMessageContent(message.content, message.citations)}
                          </div>
                        </div>
                      );
                    })}
                    {streamingText && (
                      <div className="flex justify-start">
                        <div className="max-w-[82%] rounded border border-zinc-800 bg-zinc-950/80 p-4 text-sm leading-6 text-zinc-200">
                          {renderMessageContent(streamingText)}
                          <span className="ml-1 inline-block h-4 w-1 animate-pulse bg-emerald-300 align-middle" />
                        </div>
                      </div>
                    )}
                    <div ref={messagesEndRef} />
                  </div>
                )}
              </div>

              <div className="shrink-0 border-t border-zinc-900 bg-[#0b0c0f] p-4">
                <form onSubmit={(event) => handleSendChatMessage(event)} className="mx-auto max-w-4xl rounded border border-zinc-800 bg-zinc-950/80 p-3">
                  <div className="mb-3 flex items-center justify-between gap-3">
                    <div className="flex items-center gap-2">
                      <span className="flex h-8 w-8 items-center justify-center rounded border border-emerald-400/20 bg-emerald-400/10 text-emerald-200">
                        <Bot className="h-4 w-4" />
                      </span>
                      <div>
                        <div className="text-sm font-semibold text-white">Atlas AI</div>
                        <div className="text-xs text-zinc-500">
                          {readySources.length > 0 ? "Ask across this notebook with citations." : "Say hi now, or add sources for grounded answers."}
                        </div>
                      </div>
                    </div>
                    <span className="hidden rounded border border-zinc-800 bg-zinc-900 px-2 py-1 text-[10px] uppercase tracking-wide text-zinc-500 sm:inline">
                      {readySources.length} sources
                    </span>
                  </div>
                  <div className="flex items-center gap-3">
                    <input
                      value={chatInput}
                      onChange={(event) => setChatInput(event.target.value)}
                      disabled={chatLoading || !selectedSessionId}
                      placeholder={readySources.length === 0 ? "Say hi, or add sources for grounded questions" : "Ask Atlas AI a cited question"}
                      className="h-12 min-w-0 flex-1 rounded border border-zinc-800 bg-[#090a0d] px-4 text-sm text-zinc-100 outline-none placeholder:text-zinc-600 focus:border-zinc-600 disabled:opacity-50"
                    />
                    <button
                      type="submit"
                      disabled={chatLoading || !chatInput.trim() || !selectedSessionId}
                      className="flex h-12 w-12 shrink-0 items-center justify-center rounded bg-emerald-300 text-zinc-950 hover:bg-emerald-200 disabled:cursor-not-allowed disabled:opacity-40"
                      title="Send"
                    >
                      {chatLoading ? <Loader2 className="h-5 w-5 animate-spin" /> : <Send className="h-5 w-5" />}
                    </button>
                  </div>
                  {readySources.length === 0 && (
                    <p className="mt-2 text-xs text-zinc-500">
                      Atlas AI can greet you immediately. Source-grounded answers, Studio, and audio unlock after a source is indexed.
                    </p>
                  )}
                </form>
              </div>
            </section>
          )}

          {view === "notes" && (
            <section className="flex min-h-0 flex-1 flex-col p-5">
              <div className="mb-4 flex items-center justify-between">
                <div>
                  <h1 className="text-xl font-semibold text-white">Notebook notes</h1>
                  <p className="mt-1 text-sm text-zinc-500">Saved locally for this notebook.</p>
                </div>
                <button
                  type="button"
                  onClick={handleSaveNotesAsSource}
                  disabled={!notes.trim() || notesSaving || !selectedWorkspace}
                  className="flex h-10 items-center gap-2 rounded bg-zinc-100 px-3 text-sm font-semibold text-zinc-950 hover:bg-white disabled:opacity-40"
                >
                  {notesSaving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Upload className="h-4 w-4" />}
                  Add as source
                </button>
              </div>
              <textarea
                value={notes}
                onChange={(event) => setNotes(event.target.value)}
                className="min-h-0 flex-1 resize-none rounded border border-zinc-800 bg-zinc-950/70 p-5 text-sm leading-6 text-zinc-100 outline-none placeholder:text-zinc-600 focus:border-zinc-600"
                placeholder="Write research notes, open questions, and synthesis drafts."
              />
            </section>
          )}

          {view === "studio" && (
            <section className="grid min-h-0 flex-1 grid-cols-[320px_minmax(0,1fr)] gap-4 p-5 max-lg:grid-cols-1">
              <div className="min-h-0 overflow-y-auto rounded border border-zinc-800 bg-zinc-950/60 p-4">
                <div className="mb-4 flex items-center justify-between">
                  <h1 className="text-lg font-semibold text-white">Studio</h1>
                  <span className="text-xs text-zinc-500">{studioOutputs.length} outputs</span>
                </div>
                <div className="grid grid-cols-2 gap-2">
                  {STUDIO_CARDS.map((card) => {
                    const Icon = card.icon;
                    return (
                      <button
                        key={card.id}
                        type="button"
                        onClick={() => generateStudioOutput(card.id)}
                        className={`rounded border p-3 text-left ${card.accent} hover:bg-opacity-20`}
                      >
                        <Icon className="h-4 w-4" />
                        <div className="mt-2 text-sm font-semibold text-white">{card.label}</div>
                      </button>
                    );
                  })}
                </div>

                <div className="mt-5 space-y-2">
                  {studioOutputs.map((output) => (
                    <button
                      key={output.id}
                      type="button"
                      onClick={() => setOpenOutput(output)}
                      className={`w-full rounded border p-3 text-left transition ${
                        openOutput?.id === output.id ? "border-zinc-600 bg-zinc-900" : "border-zinc-800 bg-zinc-950 hover:bg-zinc-900/70"
                      }`}
                    >
                      <div className="flex items-center justify-between gap-3">
                        <div className="min-w-0">
                          <div className="truncate text-sm font-medium text-white">{output.title}</div>
                          <div className="mt-1 text-[11px] uppercase tracking-wide text-zinc-500">{outputLabel(output.output_type)}</div>
                        </div>
                        <div className="flex items-center gap-2">
                          {(output.status === "pending" || output.status === "processing") && <Loader2 className="h-4 w-4 animate-spin text-amber-300" />}
                          {output.status === "ready" && <CheckCircle2 className="h-4 w-4 text-emerald-300" />}
                          {output.status === "failed" && <AlertTriangle className="h-4 w-4 text-red-300" />}
                        </div>
                      </div>
                    </button>
                  ))}
                </div>
              </div>

              <div className="min-h-0 overflow-y-auto rounded border border-zinc-800 bg-zinc-950/40 p-5">
                <div className="mb-4 flex items-center justify-between">
                  <div>
                    <h2 className="text-lg font-semibold text-white">{openOutput?.title || "Output viewer"}</h2>
                    {openOutput && <div className="mt-1 text-xs text-zinc-500">{outputLabel(openOutput.output_type)} - {openOutput.status}</div>}
                  </div>
                  {openOutput && (
                    <button
                      type="button"
                      onClick={() => handleDeleteStudioOutput(openOutput.id)}
                      className="flex h-9 w-9 items-center justify-center rounded border border-zinc-800 text-zinc-500 hover:border-red-500/30 hover:bg-red-500/10 hover:text-red-200"
                      title="Delete output"
                    >
                      <Trash2 className="h-4 w-4" />
                    </button>
                  )}
                </div>
                {renderOutputPreview(openOutput)}
              </div>
            </section>
          )}

          {view === "canvas" && (
            renderSourceMap()
          )}

          {view === "agent" && (
            <section className="min-h-0 flex-1 overflow-y-auto p-5">
              <div className="grid gap-4 lg:grid-cols-2">
                <button
                  type="button"
                  onClick={() => setView("ask")}
                  className="rounded border border-emerald-400/20 bg-emerald-400/10 p-5 text-left hover:bg-emerald-400/15"
                >
                  <Bot className="h-5 w-5 text-emerald-200" />
                  <div className="mt-3 text-lg font-semibold text-white">Source expert</div>
                  <div className="mt-2 text-sm text-zinc-400">Grounded Q&A, citations, scoped synthesis.</div>
                </button>
                <button
                  type="button"
                  onClick={() => setDeepResearchOpen(true)}
                  className="rounded border border-sky-400/20 bg-sky-400/10 p-5 text-left hover:bg-sky-400/15"
                >
                  <Search className="h-5 w-5 text-sky-200" />
                  <div className="mt-3 text-lg font-semibold text-white">Source discovery</div>
                  <div className="mt-2 text-sm text-zinc-400">Find sources, ingest selected results, continue in the notebook.</div>
                </button>
                <div className="rounded border border-zinc-800 bg-zinc-950/60 p-5">
                  <FileText className="h-5 w-5 text-violet-200" />
                  <div className="mt-3 text-lg font-semibold text-white">Deliverable builder</div>
                  <div className="mt-2 text-sm text-zinc-400">Reports, guides, quizzes, flashcards, maps.</div>
                </div>
                <div className="rounded border border-zinc-800 bg-zinc-950/60 p-5">
                  <Video className="h-5 w-5 text-amber-200" />
                  <div className="mt-3 text-lg font-semibold text-white">Video briefs</div>
                  <div className="mt-2 text-sm text-zinc-400">Short video and narrated slide generation need the next backend service.</div>
                </div>
              </div>
            </section>
          )}
        </main>

        <aside className="flex min-h-0 flex-col overflow-y-auto border-l border-zinc-900 bg-[#0b0c0f] p-4 max-xl:hidden">
          <div className="rounded border border-zinc-800 bg-zinc-950/70 p-4">
            <div className="flex items-center justify-between">
              <div>
                <h2 className="text-sm font-semibold text-white">Notebook state</h2>
                <p className="mt-1 text-xs text-zinc-500">{selectedWorkspace?.name || "No notebook"}</p>
              </div>
              <span className={`rounded px-2 py-1 text-[10px] font-semibold uppercase ${
                engineStatus === "active" ? "bg-emerald-400/10 text-emerald-200" : "bg-zinc-800 text-zinc-400"
              }`}>
                {engineStatus === "active" ? "AI ready" : "Local"}
              </span>
            </div>
            <div className="mt-4 grid grid-cols-3 gap-2">
              <div>
                <div className="text-xl font-semibold text-white">{sources.length}</div>
                <div className="text-[10px] uppercase tracking-wide text-zinc-500">Sources</div>
              </div>
              <div>
                <div className="text-xl font-semibold text-white">{messages.length}</div>
                <div className="text-[10px] uppercase tracking-wide text-zinc-500">Messages</div>
              </div>
              <div>
                <div className="text-xl font-semibold text-white">{studioOutputs.length}</div>
                <div className="text-[10px] uppercase tracking-wide text-zinc-500">Outputs</div>
              </div>
            </div>
          </div>

          <div className="mt-4 rounded border border-zinc-800 bg-zinc-950/70 p-4">
            <h2 className="text-sm font-semibold text-white">Generate</h2>
            <div className="mt-3 grid grid-cols-2 gap-2">
              {STUDIO_CARDS.map((card) => {
                const Icon = card.icon;
                return (
                  <button
                    key={card.id}
                    type="button"
                    onClick={() => generateStudioOutput(card.id)}
                    className="rounded border border-zinc-800 bg-zinc-900/40 p-3 text-left hover:bg-zinc-900"
                  >
                    <Icon className="h-4 w-4 text-zinc-300" />
                    <div className="mt-2 text-xs font-semibold text-white">{card.label}</div>
                  </button>
                );
              })}
            </div>
          </div>

          {selectedWorkspace && token && (
            <div className="mt-4 rounded border border-zinc-800 bg-zinc-950/70 p-4">
              <AudioOverviewPanel
                workspaceId={selectedWorkspace.id}
                token={token}
                docIds={readySources.map((source) => source.id)}
              />
            </div>
          )}

          <div className="mt-4 rounded border border-zinc-800 bg-zinc-950/70 p-4">
            <h2 className="text-sm font-semibold text-white">Agent actions</h2>
            <div className="mt-3 space-y-2">
              <button
                type="button"
                onClick={() => setDeepResearchOpen(true)}
                className="flex w-full items-center justify-between rounded border border-zinc-800 bg-zinc-900/40 px-3 py-2 text-sm text-zinc-200 hover:bg-zinc-900"
              >
                <span className="flex items-center gap-2"><Search className="h-4 w-4" /> Discover sources</span>
                <ChevronRight className="h-4 w-4 text-zinc-600" />
              </button>
              <button
                type="button"
                onClick={() => setView("notes")}
                className="flex w-full items-center justify-between rounded border border-zinc-800 bg-zinc-900/40 px-3 py-2 text-sm text-zinc-200 hover:bg-zinc-900"
              >
                <span className="flex items-center gap-2"><BookOpen className="h-4 w-4" /> Open notes</span>
                <ChevronRight className="h-4 w-4 text-zinc-600" />
              </button>
              <button
                type="button"
                onClick={() => setView("canvas")}
                className="flex w-full items-center justify-between rounded border border-zinc-800 bg-zinc-900/40 px-3 py-2 text-sm text-zinc-200 hover:bg-zinc-900"
              >
                <span className="flex items-center gap-2"><Map className="h-4 w-4" /> Map sources</span>
                <ChevronRight className="h-4 w-4 text-zinc-600" />
              </button>
            </div>
          </div>
        </aside>
      </div>

      {selectedCitation && (
        <div className="fixed bottom-4 right-4 z-50 w-[420px] rounded border border-emerald-400/20 bg-[#0b0c0f] p-4 shadow-2xl shadow-black/60">
          <div className="mb-3 flex items-center justify-between">
            <div>
              <div className="text-xs font-semibold uppercase tracking-wide text-emerald-200">Citation</div>
              <div className="mt-1 max-w-[340px] truncate text-sm font-medium text-white">
                {selectedCitation.filename || "Source"}
              </div>
            </div>
            <button type="button" onClick={() => setSelectedCitation(null)} className="text-zinc-500 hover:text-white">
              Close
            </button>
          </div>
          <div className="mb-3 text-xs text-zinc-500">
            {selectedCitation.file_type === "youtube" && selectedCitation.source_url ? (
              <a
                href={`${selectedCitation.source_url}&t=${parseTimeToSeconds(extractYoutubeTimestamp(selectedCitation.content || selectedCitation.text || ""))}s`}
                target="_blank"
                rel="noopener noreferrer"
                className="text-emerald-200 hover:underline"
              >
                Open video timestamp
              </a>
            ) : (
              citationLabel({
                page: selectedCitation.page_number,
                sheet: selectedCitation.sheet,
                timestamp: selectedCitation.timestamp,
                origin: selectedCitation.origin,
                source_label: selectedCitation.source_label,
                external_url: selectedCitation.external_url,
                venue: selectedCitation.venue,
              })
            )}
          </div>
          <p className="max-h-44 overflow-y-auto rounded border border-zinc-800 bg-zinc-950 p-3 text-sm leading-6 text-zinc-300">
            {selectedCitation.content || selectedCitation.text || "No source text available."}
          </p>
        </div>
      )}

      {showAddSource && selectedWorkspace && (
        <AddSourceModal
          notebookId={selectedWorkspace.id}
          token={token}
          onClose={() => setShowAddSource(false)}
          onAdded={() => {
            setShowAddSource(false);
            fetchDocuments(selectedWorkspace.id);
          }}
        />
      )}

      {deepResearchOpen && selectedWorkspace && (
        <DeepResearchDrawer
          open={deepResearchOpen}
          onClose={() => setDeepResearchOpen(false)}
          workspaceId={selectedWorkspace.id}
          token={token}
          onIngested={() => fetchDocuments(selectedWorkspace.id)}
        />
      )}

      <OnboardingTour />
    </div>
  );
}
