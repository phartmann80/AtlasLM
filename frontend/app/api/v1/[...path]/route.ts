import { NextResponse } from "next/server";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";
export const maxDuration = 300;

type RouteContext = {
  params: Promise<{ path?: string[] }>;
};

const BLOCKED_TARGETS = [
  "localhost",
  "127.0.0.1",
];

function configuredBackend(): string | null {
  const raw =
    process.env.ATLAS_BACKEND_URL ||
    process.env.ATLAS_VERCEL_BACKEND_URL ||
    process.env.ATLAS_API_PROXY_TARGET ||
    "";
  const target = raw.trim().replace(/\/$/, "");
  if (!target) return null;
  if (BLOCKED_TARGETS.some((blocked) => target.includes(blocked))) return null;
  return target;
}

function backendUrl(target: string, request: Request, path: string[]): string {
  const incoming = new URL(request.url);
  const base = target.endsWith("/api/v1") ? target : `${target}/api/v1`;
  const encodedPath = path.map((part) => encodeURIComponent(part)).join("/");
  return `${base}/${encodedPath}${incoming.search}`;
}

function proxyHeaders(request: Request): Headers {
  const headers = new Headers(request.headers);
  [
    "connection",
    "content-length",
    "host",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
  ].forEach((name) => headers.delete(name));
  headers.set("x-atlaslm-gateway", "vercel");
  return headers;
}

function backendNotConfigured() {
  return NextResponse.json(
    {
      detail:
        "AtlasLM backend is not configured. Set ATLAS_BACKEND_URL to the production FastAPI backend.",
    },
    { status: 503 },
  );
}

async function proxy(request: Request, context: RouteContext): Promise<Response> {
  const target = configuredBackend();
  if (!target) return backendNotConfigured();

  const { path = [] } = await context.params;
  const method = request.method.toUpperCase();
  const body =
    method === "GET" || method === "HEAD"
      ? undefined
      : await request.arrayBuffer();

  const upstream = await fetch(backendUrl(target, request, path), {
    method,
    headers: proxyHeaders(request),
    body,
    cache: "no-store",
  });

  const responseHeaders = new Headers(upstream.headers);
  responseHeaders.delete("content-encoding");
  responseHeaders.delete("content-length");
  responseHeaders.delete("transfer-encoding");

  return new Response(upstream.body, {
    status: upstream.status,
    statusText: upstream.statusText,
    headers: responseHeaders,
  });
}

export const GET = proxy;
export const HEAD = proxy;
export const POST = proxy;
export const PUT = proxy;
export const PATCH = proxy;
export const DELETE = proxy;
export const OPTIONS = proxy;
