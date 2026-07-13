const base = (process.env.ATLAS_PUBLIC_BACKEND_URL || "https://api.atlaslm.cloud").replace(/\/$/, "");

async function check(path) {
  const response = await fetch(`${base}${path}`);
  if (!response.ok) throw new Error(`${path} returned ${response.status}`);
  return response.json();
}

const health = await check("/health");
if (health.status !== "healthy") throw new Error("Backend health is not healthy");
console.log(JSON.stringify({ backend: "pass", health: "pass", base }));
