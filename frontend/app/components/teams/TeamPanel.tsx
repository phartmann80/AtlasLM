// Patch 013 - Teams / Shared Workspaces panel.
// Mount on the workspace settings page. Reuses the shared Atlas brand theme
// (app/atlas-theme.css) and the real logo via <AtlasLogo /> in the page header.
"use client";

import { useEffect, useState, useCallback } from "react";
import {
  getTeam, inviteMember, revokeInvite, changeRole, removeMember,
  type TeamState, type Role,
} from "@/lib/teams";
import "./team.css";

const ROLE_LABEL: Record<Role, string> = { owner: "Owner", editor: "Editor", viewer: "Viewer" };
const ROLE_COLOR: Record<Role, string> = {
  owner: "var(--atlas-accent-2)", editor: "var(--atlas-muted)", viewer: "var(--atlas-muted)",
};
const ROLE_DESC: Record<Role, string> = {
  owner: "Billing, delete workspace, full control",
  editor: "Add sources, run studio, invite viewers",
  viewer: "Read and listen only",
};

function colorFor(seed: string): string {
  const palette = ["#FF3B00", "#A8A29E", "#3F8F6B", "#F08830", "#78716C"];
  let h = 0;
  for (let i = 0; i < seed.length; i++) h = (h * 31 + seed.charCodeAt(i)) | 0;
  return palette[Math.abs(h) % palette.length];
}

function initials(s: string): string {
  const parts = s.replace(/@.*/, "").split(/[.\s_-]+/).filter(Boolean);
  return (parts[0]?.[0] || "?").concat(parts[1]?.[0] || "").toUpperCase();
}

export default function TeamPanel({ workspaceId, seatLimit = 5 }: { workspaceId: string; seatLimit?: number }) {
  const [state, setState] = useState<TeamState | null>(null);
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<Role>("viewer");
  const [error, setError] = useState("");
  const [toast, setToast] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try { setState(await getTeam(workspaceId)); }
    catch (e: any) { setError(e.message); }
  }, [workspaceId]);

  useEffect(() => { load(); }, [load]);

  function flash(m: string) { setToast(m); window.setTimeout(() => setToast(""), 2600); }

  const yourRole = state?.your_role ?? "viewer";
  const canManage = yourRole === "owner";
  const canInvite = yourRole === "owner" || yourRole === "editor";
  const used = (state?.members.length ?? 0) + (state?.invites.length ?? 0);

  async function onInvite(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    const v = email.trim().toLowerCase();
    if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(v)) { setError("Enter a valid email address."); return; }
    if (used >= seatLimit) { setError("No seats left on this plan. Upgrade to add more."); return; }
    setBusy(true);
    try {
      await inviteMember(workspaceId, v, role);
      setEmail("");
      flash("Invite sent to " + v);
      await load();
    } catch (e: any) { setError(e.message); }
    finally { setBusy(false); }
  }

  if (!state) {
    return <div className="team-wrap" style={{ color: "var(--atlas-muted)", padding: 16 }}>Loading team...</div>;
  }

  return (
    <div className="team-wrap">
      <div className="team-card" style={{ padding: 16 }}>
        <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 10 }}>
          <span style={{ fontSize: 13, color: "var(--atlas-muted)" }}>Seats used</span>
          <span style={{ fontSize: 13, fontWeight: 700 }}>{used} of {seatLimit}</span>
        </div>
        <div className="team-seatbar">
          <div className="team-seatfill" style={{ width: `${Math.min(100, (used / seatLimit) * 100)}%` }} />
        </div>
      </div>

      {canInvite && (
        <form className="team-card" style={{ padding: 16 }} onSubmit={onInvite}>
          <div style={{ fontWeight: 700, marginBottom: 12, fontSize: 14 }}>Invite a teammate</div>
          <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
            <input
              className="team-input" style={{ flex: "1 1 260px", minWidth: 200 }}
              placeholder="name@company.com" value={email}
              onChange={(e) => { setEmail(e.target.value); setError(""); }}
              aria-label="Email to invite"
            />
            <select className="team-select" value={role} onChange={(e) => setRole(e.target.value as Role)} aria-label="Role">
              <option value="viewer">Viewer</option>
              {/* Editors can invite viewers only; the server enforces this too. */}
              {canManage && <option value="editor">Editor</option>}
            </select>
            <button className="team-btn atlas-cta" type="submit" disabled={busy}>
              {busy ? "Sending" : "Send invite"}
            </button>
          </div>
          {error && <div style={{ color: "var(--atlas-danger)", fontSize: 13, marginTop: 10 }}>{error}</div>}
          <div style={{ color: "var(--atlas-muted)", fontSize: 12, marginTop: 10 }}>{ROLE_DESC[role]}</div>
        </form>
      )}

      <div className="team-card">
        <div className="team-card-head">
          Members <span style={{ color: "var(--atlas-muted)", fontWeight: 500 }}>({state.members.length})</span>
        </div>
        {state.members.map((m) => (
          <div className="team-row" key={m.id}>
            <div className="team-avatar" style={{ background: colorFor(m.user_id) }}>{initials(m.user_id)}</div>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontWeight: 600, fontSize: 14 }}>{m.user_id}</div>
            </div>
            {m.role === "owner" || !canManage ? (
              <span className="team-pill" style={{ color: ROLE_COLOR[m.role] }}>
                <span style={{ width: 6, height: 6, borderRadius: 999, background: ROLE_COLOR[m.role] }} />
                {ROLE_LABEL[m.role]}
              </span>
            ) : (
              <select
                className="team-select" value={m.role}
                onChange={async (e) => { await changeRole(workspaceId, m.user_id, e.target.value as Role); flash("Role updated"); load(); }}
                aria-label={"Role for " + m.user_id}
              >
                <option value="editor">Editor</option>
                <option value="viewer">Viewer</option>
              </select>
            )}
            {canManage && m.role !== "owner" && (
              <button className="team-btn team-ghost"
                onClick={async () => { await removeMember(workspaceId, m.user_id); flash("Member removed"); load(); }}
                aria-label={"Remove " + m.user_id}>Remove</button>
            )}
          </div>
        ))}
      </div>

      {state.invites.length > 0 && (
        <div className="team-card">
          <div className="team-card-head">
            Pending invites <span style={{ color: "var(--atlas-muted)", fontWeight: 500 }}>({state.invites.length})</span>
          </div>
          {state.invites.map((i) => (
            <div className="team-row" key={i.id}>
              <div className="team-avatar" style={{ background: "transparent", border: "1px dashed var(--atlas-line)", color: "var(--atlas-muted)" }}>@</div>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontWeight: 600, fontSize: 14 }}>{i.email}</div>
                <div style={{ color: "var(--atlas-muted)", fontSize: 13 }}>Waiting to be claimed</div>
              </div>
              <span className="team-pill" style={{ color: ROLE_COLOR[i.role] }}>
                <span style={{ width: 6, height: 6, borderRadius: 999, background: ROLE_COLOR[i.role] }} />
                {ROLE_LABEL[i.role]}
              </span>
              {canInvite && (
                <button className="team-btn team-ghost"
                  onClick={async () => { await revokeInvite(workspaceId, i.id); flash("Invite revoked"); load(); }}>Revoke</button>
              )}
            </div>
          ))}
        </div>
      )}

      {toast && (
        <div role="status" style={{
          position: "fixed", bottom: 22, left: "50%", transform: "translateX(-50%)",
          background: "var(--atlas-surface)", border: "1px solid var(--atlas-line)",
          color: "var(--atlas-text)", padding: "10px 16px", borderRadius: 10,
          fontSize: 13, fontWeight: 600, boxShadow: "0 8px 24px rgba(0,0,0,0.4)",
        }}>{toast}</div>
      )}
    </div>
  );
}
