export class ApiError extends Error {
  status: number;
  detail: unknown;
  constructor(status: number, detail: unknown) {
    super(typeof detail === "string" ? detail : "Request failed");
    this.status = status;
    this.detail = detail;
  }
}

function message(detail: unknown): unknown {
  if (Array.isArray(detail)) {
    return detail.map((d) => `${(d.loc || []).slice(1).join(".")}: ${d.msg}`).join(" · ");
  }
  if (detail && typeof detail === "object" && "message" in (detail as object)) {
    return (detail as { message: string }).message;
  }
  return detail;
}

/** Browser-side API call. Same origin, cookie session. */
export async function api<T = any>(path: string, init: RequestInit & { json?: unknown } = {}): Promise<T> {
  const { json, ...rest } = init;
  const res = await fetch(`/api${path}`, {
    credentials: "include",
    ...rest,
    headers: json !== undefined ? { "Content-Type": "application/json", ...(rest.headers || {}) } : rest.headers,
    body: json !== undefined ? JSON.stringify(json) : rest.body,
  });
  if (!res.ok) {
    let detail: unknown = res.statusText;
    try {
      detail = (await res.json()).detail;
    } catch {}
    throw new ApiError(res.status, message(detail));
  }
  return res.status === 204 ? (undefined as T) : res.json();
}

/** Server-side fetch (server components): talks to the API over the internal network. */
export async function serverApi<T = any>(path: string, revalidate = 60): Promise<T | null> {
  const base = process.env.API_INTERNAL_URL || "http://localhost:8000";
  try {
    const res = await fetch(`${base}/api${path}`, { next: { revalidate } });
    return res.ok ? res.json() : null;
  } catch {
    return null;
  }
}

export const SITE_URL = process.env.NEXT_PUBLIC_SITE_URL || "http://localhost:3000";
