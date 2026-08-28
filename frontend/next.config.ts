import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // API requests are proxied by app/api/v1/[...path] to the owned AtlasLM
  // FastAPI backend through ATLAS_BACKEND_URL. Production is not on Vercel.
  turbopack: {
    root: __dirname,
  },
};

export default nextConfig;
