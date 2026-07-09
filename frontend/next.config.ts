import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // API requests are proxied by app/api/v1/[...path] so production can target
  // either a Vercel backend or the dedicated AtlasLM server via ATLAS_BACKEND_URL.
};

export default nextConfig;
