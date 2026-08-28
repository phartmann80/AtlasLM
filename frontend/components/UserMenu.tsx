"use client";

import { useState, useEffect } from "react";
import { supabaseBrowser, getCurrentProfile, signOut, type AtlasProfile } from "@/lib/supabaseClient";
import { useRouter } from "next/navigation";

export default function UserMenu() {
  const router = useRouter();
  const [user, setUser] = useState<AtlasProfile | { email?: string } | null>(null);
  const [tier, setTier] = useState<string>("Free");
  const [open, setOpen] = useState(false);

  useEffect(() => {
    const loadProfile = async () => {
      const profile = await getCurrentProfile();
      if (profile) {
        setUser(profile);
        setTier(profile.tier);
      } else {
        // Fallback: check getUser directly
        const supabase = supabaseBrowser();
        const { data } = await supabase.auth.getUser();
        if (data?.user) {
          setUser(data.user);
        }
      }
    };
    loadProfile();
  }, []);

  const handleLogout = async () => {
    await signOut();
    
    // Clear AtlasLM session state for clean user handoff
    if (typeof window !== 'undefined') {
      localStorage.removeItem("selectedWorkspaceId");
      localStorage.removeItem("selectedSessionId");
      localStorage.removeItem("atlas:selected-workspace");
    }
    
    router.push("/login");
  };

  if (!user) return null;

  const email = user.email || "User";
  const initial = email.charAt(0).toUpperCase();

  return (
    <div className="relative text-sm">
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-2 py-1.5 px-3 rounded-lg bg-zinc-900 border border-zinc-800 hover:border-zinc-700 transition-colors"
      >
        <div className="w-7 h-7 rounded-full bg-gradient-to-br from-orange-600 to-red-600 flex items-center justify-center text-white font-bold">
          {initial}
        </div>
        <div className="flex flex-col text-left">
          <span className="text-zinc-200 font-semibold leading-tight">{email}</span>
          <span className="text-[10px] text-orange-500 font-bold uppercase">{tier}</span>
        </div>
      </button>

      {open && (
        <div className="absolute right-0 mt-2 w-44 rounded-xl bg-zinc-900 border border-zinc-800 shadow-lg overflow-hidden z-50">
          <button
            onClick={() => router.push("/account")}
            className="w-full text-left px-4 py-2 text-zinc-200 hover:bg-zinc-800"
          >
            Account
          </button>
          <button
            onClick={() => router.push("/billing")}
            className="w-full text-left px-4 py-2 text-zinc-200 hover:bg-zinc-800"
          >
            Billing
          </button>
          <button
            onClick={handleLogout}
            className="w-full text-left px-4 py-2 text-red-400 hover:bg-zinc-800 hover:text-red-300 border-t border-zinc-800"
          >
            Logout
          </button>
        </div>
      )}
    </div>
  );
}