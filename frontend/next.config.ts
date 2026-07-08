import type { NextConfig } from "next";

const apiProxyTarget = (
  process.env.ATLAS_API_PROXY_TARGET || "http://85.215.225.0:8080"
).replace(/\/$/, "");

const nextConfig: NextConfig = {
  async rewrites() {
    return [
      {
        source: "/api/v1/:path*",
        destination: `${apiProxyTarget}/api/v1/:path*`,
      },
    ];
  },
};

export default nextConfig;
