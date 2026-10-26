import { render } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { App } from "../App";
import { AppProviders } from "../components/AppProviders";
import { unmocked } from "./unmocked";

export const USER = {
  id: "11111111-1111-1111-1111-111111111111",
  email: "asha@example.com",
  display_name: "Asha",
  created_at: "2026-10-24T00:00:00Z",
};

export const authBody = (token = "access-1") => ({
  access_token: token,
  token_type: "bearer",
  expires_in: 900,
  user: USER,
});

export const errorBody = (code: string, message: string, details: unknown = null) => ({
  error: { code, message, details, request_id: "req1" },
});

export type Handler = (req: { body: unknown; headers: Headers }) => Response | Promise<Response>;

export function json(status: number, body?: unknown): Response {
  return new Response(body === undefined ? null : JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

/** Stub fetch with handlers keyed "METHOD /path" (path relative to /api/v1). Records calls. */
export function mockApi(routes: Record<string, Handler>) {
  const calls: { key: string; body: unknown; headers: Headers }[] = [];
  const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    const key = `${init?.method ?? "GET"} ${url.replace("/api/v1", "")}`;
    const headers = new Headers(init?.headers);
    const raw = init?.body;
    const body = raw instanceof FormData ? raw : raw ? JSON.parse(raw as string) : undefined;
    calls.push({ key, body, headers });
    const handler = routes[key];
    if (!handler) {
      unmocked.push(key);
      throw new Error(`Unmocked request: ${key}`);
    }
    const pending = Promise.resolve(handler({ body, headers }));
    const signal = init?.signal;
    if (!signal) return pending;
    // Like a real fetch, reject when the caller aborts.
    return Promise.race([
      pending,
      new Promise<Response>((_, reject) => {
        const abort = () => reject(new DOMException("Aborted", "AbortError"));
        if (signal.aborted) abort();
        else signal.addEventListener("abort", abort, { once: true });
      }),
    ]);
  });
  vi.stubGlobal("fetch", fetchMock);
  return { calls, fetchMock };
}

export function renderApp(initialPath = "/") {
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <AppProviders>
        <App />
      </AppProviders>
    </MemoryRouter>,
  );
}

export const aiStatus = {
  ollama: {
    enabled: false, base_url: "http://localhost:11434", reachable: null, error: null,
    text_model: { name: null, configured: false, installed: null },
    vision_model: { name: null, configured: false, installed: null },
  },
  external_providers_allowed: false,
  fallback_policy: "none",
};

export function blob(type = "image/jpeg"): Response {
  return new Response(new Uint8Array([1, 2, 3, 4]), { status: 200, headers: { "Content-Type": type } });
}

export const MODULES = [
  { key: "food_recognition", title: "Food recognition & nutrition", description: "Identify a dish.", available: false },
  { key: "freshness", title: "Freshness check", description: "Visible freshness signs.", available: false },
  { key: "hygiene", title: "Kitchen hygiene", description: "Visible hygiene concerns.", available: false },
  { key: "cooking", title: "Cooking assistant", description: "Recipe help.", available: false },
  { key: "meal_planning", title: "Meal planning", description: "Plans and grocery lists.", available: false },
];

export const emptySummary = {
  media: { count: 0, total_bytes: 0, quota_bytes: 524288000, max_upload_bytes: 8388608 },
  history: { total: 0, by_module: {} },
  recent: [],
};

export const MEDIA_ITEM = {
  id: "m1", kind: "image", content_type: "image/jpeg", display_name: "lunch.jpg",
  size_bytes: 204800, width: 800, height: 600, duration_seconds: null,
  created_at: "2026-10-20T10:00:00Z",
};

export const HISTORY_ITEM = {
  id: "h1", module: "freshness", status: "completed", title: "Tomato check",
  summary: "Looks fresh", media_id: null, created_at: "2026-10-21T09:30:00Z",
};

export const page = <T,>(items: T[], over: Partial<{ total: number; page: number; page_size: number; pages: number }> = {}) => ({
  items,
  total: items.length,
  page: 1,
  page_size: 10,
  pages: items.length ? 1 : 0,
  ...over,
});

/** Default handlers for everything the dashboard loads; override per test. */
export function dashboardRoutes(over: Record<string, Handler> = {}): Record<string, Handler> {
  return {
    "GET /dashboard/summary": () => json(200, emptySummary),
    "GET /modules": () => json(200, MODULES),
    "GET /ai/status": () => json(200, aiStatus),
    ...over,
  };
}

/**
 * jsdom's XMLHttpRequest cannot reach our fetch mock, and uploads use XHR for progress events.
 * This stand-in reports 50% progress, then forwards the request to the stubbed fetch so the same
 * handlers (and call recording) apply.
 */
export function stubUploadXhr() {
  class FakeXhr {
    upload: { onprogress: ((e: { lengthComputable: boolean; loaded: number; total: number }) => void) | null } = { onprogress: null };
    onload: (() => void) | null = null;
    onerror: (() => void) | null = null;
    onabort: (() => void) | null = null;
    status = 0;
    responseText = "";
    withCredentials = false;
    private method = "GET";
    private url = "";
    private headers: Record<string, string> = {};
    private aborted = false;
    open(method: string, url: string) { this.method = method; this.url = url; }
    setRequestHeader(name: string, value: string) { this.headers[name] = value; }
    abort() { this.aborted = true; this.onabort?.(); }
    send(body: FormData) {
      this.upload.onprogress?.({ lengthComputable: true, loaded: 50, total: 100 });
      fetch(this.url, { method: this.method, headers: this.headers, body }).then(
        async (r) => {
          if (this.aborted) return;
          this.status = r.status;
          this.responseText = await r.text();
          this.onload?.();
        },
        () => !this.aborted && this.onerror?.(),
      );
    }
  }
  vi.stubGlobal("XMLHttpRequest", FakeXhr);
}
