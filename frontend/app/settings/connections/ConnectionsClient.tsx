"use client";

import { useEffect, useState } from "react";
import { supabaseBrowser } from "@/lib/supabaseClient";
import GoogleConnectorPanel from "@/app/components/connections/GoogleConnectorPanel";
import LiveSyncPanel from "@/app/components/connections/LiveSyncPanel";
import Header from "@/components/layout/header";
import Footer from "@/components/layout/footer";
import Link from "next/link";
import { apiUrl } from "@/lib/apiBase";

type DriveSource = { source_id: string; file_id: string; name: string; kind: string };

export default function ConnectionsClient() {
  const [token, setToken] = useState<string>("");
  const [workspaceId, setWorkspaceId] = useState<string>("");
  const [loading, setLoading] = useState(true);
  const [driveSources, setDriveSources] = useState<DriveSource[]>([]);

  useEffect(() => {
    async function loadSession() {
      try {
        const supabase = supabaseBrowser();
        const { data: { session } } = await supabase.auth.getSession();
        const tok = session?.access_token ?? "";
        if (tok) setToken(tok);
        const wsId = typeof window !== "undefined" ? localStorage.getItem("selectedWorkspaceId") || "" : "";
        setWorkspaceId(wsId);

        // Fetch Drive-imported documents so LiveSyncPanel can list them
        if (wsId && tok) {
          try {
            const res = await fetch(apiUrl(`/workspaces/${wsId}/documents`), {
              headers: { Authorization: `Bearer ${tok}` },
            });
            if (res.ok) {
              interface DocItem {
                id: string;
                origin: string;
                filename: string;
                file_type: string;
                external_url?: string;
              }
              const docs: DocItem[] = await res.json();
              setDriveSources(
                docs
                  .filter((d) => d.origin === "google_drive")
                  .map((d) => ({
                    source_id: d.id,
                    file_id: d.external_url?.replace("google-drive://", "") ?? "",
                    name: d.filename,
                    kind: d.file_type,
                  }))
              );
            }
          } catch {
            // non-fatal: LiveSyncPanel just shows empty list
          }
        }
      } catch (err) {
        console.error("Failed to load session:", err);
      } finally {
        setLoading(false);
      }
    }
    loadSession();
  }, []);

  if (loading) {
    return (
      <div className="relative min-h-screen bg-zinc-950 flex flex-col justify-between overflow-hidden text-zinc-100">
        <Header />
        <main className="flex-grow pt-32 pb-24 px-6 max-w-3xl mx-auto relative z-10 flex items-center justify-center">
          <div className="text-zinc-400 text-sm">Loading settings...</div>
        </main>
        <Footer />
      </div>
    );
  }

  return (
    <div className="relative min-h-screen bg-zinc-950 flex flex-col justify-between overflow-hidden text-zinc-100">
      {/* Background glow effects */}
      <div className="absolute inset-0 radial-glow pointer-events-none" />
      <div className="absolute inset-0 radial-glow-purple pointer-events-none" />

      <Header />

      <main className="flex-grow pt-32 pb-24 px-6 w-full max-w-3xl mx-auto relative z-10">
        <div className="mb-8">
          <Link href="/dashboard" className="text-zinc-400 hover:text-zinc-200 text-sm flex items-center gap-2 mb-6 transition-colors">
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
              <path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7" />
            </svg>
            Back to Dashboard
          </Link>
          <h1 className="text-3xl font-extrabold text-white tracking-tight mb-2">Connections</h1>
          <p className="text-zinc-400 text-sm">
            Manage your external integrations and import documents directly into your workspace.
          </p>
        </div>

        <div className="bg-zinc-900/40 border border-zinc-900 rounded-2xl p-6 backdrop-blur-md">
          {workspaceId ? (
            <GoogleConnectorPanel workspaceId={workspaceId} token={token} />
          ) : (
            <div className="text-zinc-400 text-sm py-4">
              Please select a workspace on the dashboard first.
            </div>
          )}
        </div>

        {workspaceId && (
          <div className="mt-6">
            <LiveSyncPanel
              workspaceId={workspaceId}
              token={token}
              sources={driveSources}
            />
          </div>
        )}
      </main>

      <Footer />
    </div>
  );
}
