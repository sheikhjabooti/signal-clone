import type { Session } from "./types";

export const API_BASE = (process.env.NEXT_PUBLIC_API_BASE || "").replace(/\/$/, "");
let csrf = "";
export function setSession(session: Session | null) { csrf = session?.csrf_token || ""; }

export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string) { super(message); }
}

export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers);
  const isForm = typeof FormData !== "undefined" && options.body instanceof FormData;
  if (options.body && !isForm) headers.set("Content-Type", "application/json");
  if (options.method && options.method !== "GET") headers.set("X-CSRF-Token", csrf);
  const response = await fetch(`${API_BASE}/api${path}`, {
    ...options, headers, credentials: "include", cache: "no-store",
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    if (response.status === 401 && !path.startsWith("/auth/") && path !== "/me") {
      window.dispatchEvent(new Event("session-expired"));
    }
    throw new ApiError(response.status, payload.error?.code || "request_failed",
      payload.error?.message || "Something went wrong. Please try again.");
  }
  return payload as T;
}

export function socketUrl() {
  const base = API_BASE || window.location.origin;
  return `${base.replace(/^http/, "ws")}/ws`;
}
export function assetUrl(path: string | null) { return path ? API_BASE + path : undefined; }
export function errorText(error: unknown) {
  return error instanceof Error ? error.message : "Something went wrong. Please try again.";
}
