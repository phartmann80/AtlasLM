// frontend/lib/audio.ts
// Client wrapper for the Patch 010 Audio Overview endpoints. Reuses the same
// access token the rest of the dashboard (Studio, Sources) uses.

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "/api/v1";
const API = API_BASE.endsWith("/api/v1") ? API_BASE : `${API_BASE}/api/v1`;

function authHeaders(token: string) {
  return { "Content-Type": "application/json", Authorization: `Bearer ${token}` };
}

export type ScriptLine = {
  speaker: "A" | "B";
  name: string;
  text: string;
  cite?: number | null;
  start?: number;
};

export type AudioOverview = {
  overview_id: string;
  title: string;
  duration: number;
  voice: string;
  style: string;
  transcript: ScriptLine[];
  audio_url: string;
};

export async function generateAudio(
  workspaceId: string, token: string,
  body: { title: string; style: string; voice: string; doc_ids?: string[] },
): Promise<AudioOverview> {
  const res = await fetch(`${API}/workspaces/${workspaceId}/audio/generate`, {
    method: "POST", headers: authHeaders(token), body: JSON.stringify(body),
  });
  if (!res.ok) {
    let message = "Could not generate the audio overview. Try again.";
    try {
      const payload = await res.json();
      if (typeof payload.detail === "string") message = payload.detail;
    } catch {
      // Keep the fallback message.
    }
    throw new Error(message);
  }
  return res.json();
}

export function exportUrl(
  workspaceId: string, overviewId: string, format: "pdf" | "md",
): string {
  return `${API}/workspaces/${workspaceId}/audio/${overviewId}/export?format=${format}`;
}

export async function createShareLink(
  workspaceId: string, overviewId: string, token: string,
): Promise<{ share_url: string; token: string }> {
  const res = await fetch(
    `${API}/workspaces/${workspaceId}/audio/${overviewId}/share`,
    { method: "POST", headers: authHeaders(token) },
  );
  if (!res.ok) throw new Error("Could not create the public link. Try again.");
  return res.json();
}

export async function revokeShareLink(
  workspaceId: string, overviewId: string, token: string,
): Promise<void> {
  await fetch(`${API}/workspaces/${workspaceId}/audio/${overviewId}/share`, {
    method: "DELETE", headers: authHeaders(token),
  });
}
