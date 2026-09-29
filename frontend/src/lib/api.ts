// Thin fetch wrapper. Auth is an httpOnly cookie; unsafe methods echo the CSRF cookie in a header.
export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

function csrfToken(): string {
  const m = document.cookie.match(/(?:^|;\s*)hss_csrf=([^;]+)/);
  return m ? decodeURIComponent(m[1]) : "";
}

let refreshing: Promise<boolean> | null = null;
async function tryRefresh(): Promise<boolean> {
  refreshing ??= fetch("/api/auth/refresh", {
    method: "POST",
    credentials: "same-origin",
    headers: { "X-CSRF-Token": csrfToken() },
  })
    .then((r) => r.ok)
    .finally(() => (refreshing = null));
  return refreshing;
}

export async function api<T>(path: string, init: RequestInit = {}, retry = true): Promise<T> {
  const method = (init.method ?? "GET").toUpperCase();
  const headers = new Headers(init.headers);
  if (init.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  if (method !== "GET") headers.set("X-CSRF-Token", csrfToken());
  const res = await fetch(path, { ...init, method, headers, credentials: "same-origin" });
  if (res.status === 401 && retry && !path.startsWith("/api/auth/")) {
    if (await tryRefresh()) return api<T>(path, init, false);
  }
  if (!res.ok) {
    let msg = res.statusText;
    try {
      const body = await res.json();
      msg = typeof body.detail === "string" ? body.detail : (body.detail?.[0]?.msg ?? msg);
    } catch {
      /* non-JSON error */
    }
    throw new ApiError(res.status, msg);
  }
  return res.json() as Promise<T>;
}
