/**
 * AtlasLM Centralized API Client
 *
 * Every request to the FastAPI backend must include:
 *   Authorization: Bearer <supabase_access_token>
 *
 * Use `apiClient.get / .post / .postForm / .delete / .stream` everywhere
 * in the dashboard instead of raw `fetch`. The token is resolved lazily from
 * the active Supabase browser session so it is always fresh.
 */

import { supabaseBrowser } from "@/lib/supabaseClient";
import { apiUrl } from "@/lib/apiBase";

/**
 * Resolve the current Supabase access token, throwing if the user is
 * unauthenticated (the dashboard layout already guards against this).
 */
async function getToken(): Promise<string> {
  const supabase = supabaseBrowser();
  const {
    data: { session },
  } = await supabase.auth.getSession();

  if (!session?.access_token) {
    throw new Error("No active Supabase session. Please log in again.");
  }
  return session.access_token;
}

/** Build base headers with Authorization + optional Content-Type. */
async function authHeaders(
  extra: Record<string, string> = {}
): Promise<Record<string, string>> {
  const token = await getToken();
  return {
    Authorization: `Bearer ${token}`,
    ...extra,
  };
}

/** GET  -  authenticated JSON request. */
async function get<T = unknown>(path: string): Promise<T> {
  const headers = await authHeaders({ "Content-Type": "application/json" });
  const res = await fetch(apiUrl(path), { headers });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`GET ${path} → ${res.status}: ${text}`);
  }
  return res.json() as Promise<T>;
}

/** POST  -  authenticated JSON request. */
async function post<T = unknown>(
  path: string,
  body: unknown,
  extra: Record<string, string> = {}
): Promise<T> {
  const headers = await authHeaders({ "Content-Type": "application/json", ...extra });
  const res = await fetch(apiUrl(path), {
    method: "POST",
    headers,
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`POST ${path} → ${res.status}: ${text}`);
  }
  return res.json() as Promise<T>;
}

/** POST  -  multipart/form-data (file upload). No Content-Type header; browser sets boundary. */
async function postForm<T = unknown>(
  path: string,
  formData: FormData,
  extra: Record<string, string> = {}
): Promise<T> {
  const headers = await authHeaders(extra); // no Content-Type  -  browser auto-sets it with boundary
  const res = await fetch(apiUrl(path), {
    method: "POST",
    headers,
    body: formData,
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`POST(form) ${path} → ${res.status}: ${text}`);
  }
  return res.json() as Promise<T>;
}

/** DELETE  -  authenticated request. */
async function del(path: string): Promise<void> {
  const headers = await authHeaders();
  const res = await fetch(apiUrl(path), {
    method: "DELETE",
    headers,
  });
  if (!res.ok && res.status !== 204) {
    const text = await res.text();
    throw new Error(`DELETE ${path} → ${res.status}: ${text}`);
  }
}

/**
 * POST + stream  -  for SSE/streaming endpoints.
 * Returns the raw `Response` so the caller can read it as an SSE stream.
 */
async function stream(path: string, body: unknown): Promise<Response> {
  const headers = await authHeaders({ "Content-Type": "application/json" });
  const res = await fetch(apiUrl(path), {
    method: "POST",
    headers,
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`STREAM ${path} → ${res.status}: ${text}`);
  }
  return res;
}

/**
 * POST + raw response  -  returns the raw `Response` object instead of deserializing it.
 */
async function postRaw(path: string, body: unknown): Promise<Response> {
  const headers = await authHeaders({ "Content-Type": "application/json" });
  return fetch(apiUrl(path), {
    method: "POST",
    headers,
    body: JSON.stringify(body),
  });
}

/** PATCH  -  authenticated JSON request. */
async function patch<T = unknown>(path: string, body: unknown): Promise<T> {
  const headers = await authHeaders({ "Content-Type": "application/json" });
  const res = await fetch(apiUrl(path), {
    method: "PATCH",
    headers,
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`PATCH ${path} → ${res.status}: ${text}`);
  }
  return res.json() as Promise<T>;
}

/** PUT  -  authenticated JSON request. Handles 204 No Content safely. */
async function put<T = unknown>(path: string, body: unknown): Promise<T> {
  const headers = await authHeaders({ "Content-Type": "application/json" });
  const res = await fetch(apiUrl(path), {
    method: "PUT",
    headers,
    body: JSON.stringify(body),
  });
  if (!res.ok && res.status !== 204) {
    const text = await res.text();
    throw new Error(`PUT ${path} → ${res.status}: ${text}`);
  }
  if (res.status === 204) {
    return {} as T;
  }
  return res.json() as Promise<T>;
}

export const apiClient = { get, post, postForm, del, stream, postRaw, patch, put };

