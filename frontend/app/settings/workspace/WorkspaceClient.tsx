"use client";

import { useEffect, useState } from "react";
import TeamPanel from "@/app/components/teams/TeamPanel";
import Header from "@/components/layout/header";
import Footer from "@/components/layout/footer";
import Link from "next/link";

const DEFAULT_SEAT_LIMIT = parseInt(
  process.env.NEXT_PUBLIC_DEFAULT_SEAT_LIMIT ?? "5",
  10
);

export default function WorkspaceClient() {
  const [workspaceId, setWorkspaceId] = useState<string>("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function loadSession() {
      const wsId =
        typeof window !== "undefined"
          ? localStorage.getItem("selectedWorkspaceId") || ""
          : "";
      await Promise.resolve();
      setWorkspaceId(wsId);
      setLoading(false);
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
          <Link
            href="/dashboard"
            className="text-zinc-400 hover:text-zinc-200 text-sm flex items-center gap-2 mb-6 transition-colors"
          >
            <svg
              className="w-4 h-4"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
              strokeWidth="2"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M15 19l-7-7 7-7"
              />
            </svg>
            Back to Dashboard
          </Link>
          <h1 className="text-3xl font-extrabold text-white tracking-tight mb-2">
            Team
          </h1>
          <p className="text-zinc-400 text-sm">
            Manage members, roles, and workspace access.
          </p>
        </div>

        {workspaceId ? (
          <TeamPanel
            workspaceId={workspaceId}
            seatLimit={DEFAULT_SEAT_LIMIT}
          />
        ) : (
          <div className="bg-zinc-900/40 border border-zinc-900 rounded-2xl p-6 backdrop-blur-md">
            <div className="text-zinc-400 text-sm py-4">
              Please select a workspace on the dashboard first.
            </div>
          </div>
        )}
      </main>

      <Footer />
    </div>
  );
}
