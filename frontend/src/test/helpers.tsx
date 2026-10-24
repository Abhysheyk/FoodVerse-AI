import { render } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { App } from "../App";
import { AuthProvider } from "../auth/AuthContext";

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
    const body = init?.body ? JSON.parse(init.body as string) : undefined;
    calls.push({ key, body, headers });
    const handler = routes[key];
    if (!handler) throw new Error(`Unmocked request: ${key}`);
    return handler({ body, headers });
  });
  vi.stubGlobal("fetch", fetchMock);
  return { calls, fetchMock };
}

export function renderApp(initialPath = "/") {
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <AuthProvider>
        <App />
      </AuthProvider>
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
