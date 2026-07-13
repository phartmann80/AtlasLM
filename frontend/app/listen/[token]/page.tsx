// frontend/app/listen/[token]/page.tsx
// Patch 010 - the PUBLIC, read-only listen page. This is the growth surface:
// a recipient lands here from a shared link, listens, and sees the
// "Made with AtlasLM" credit that links back. No auth, no sources exposed.
import "../../components/audio/audio-overview.css";
import PublicListen from "./PublicListen";

const SERVER_API = "http://backend:8000/api/v1";
const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "/api/v1";
const CLIENT_API = API_BASE.endsWith("/api/v1") ? API_BASE : `${API_BASE}/api/v1`;

async function getData(token: string) {
  try {
    const res = await fetch(`${SERVER_API}/public/audio/${token}`, { cache: "no-store" });
    if (!res.ok) return null;
    return res.json();
  } catch {
    return null;
  }
}

export default async function ListenPage(
  { params }: { params: Promise<{ token: string }> },
) {
  const { token } = await params;
  const data = await getData(token);
  if (!data) {
    return (
      <div className="ao-public ao-public-empty">
        <h1>This link is not available</h1>
        <p>The overview may have been unshared. Ask the sender for a new link.</p>
        <a className="ao-public-cta" href="/">Make your own with AtlasLM</a>
      </div>
    );
  }
  return <PublicListen data={data} apiBase={CLIENT_API} token={token} />;
}
