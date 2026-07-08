const rawApiBase =
  process.env.NEXT_PUBLIC_API_BASE ||
  process.env.NEXT_PUBLIC_API_URL ||
  "";

export function apiBase(): string {
  const base = rawApiBase.trim().replace(/\/$/, "");

  if (!base) {
    return "/api/v1";
  }

  return base.endsWith("/api/v1") ? base : `${base}/api/v1`;
}

export function apiUrl(path: string): string {
  const base = apiBase();
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;

  if (base.endsWith("/api/v1") && normalizedPath.startsWith("/api/v1/")) {
    return `${base}${normalizedPath.slice("/api/v1".length)}`;
  }

  return `${base}${normalizedPath}`;
}
