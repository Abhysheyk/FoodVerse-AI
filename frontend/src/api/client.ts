import type { AuthResponse } from "./types";

/**
 * API client.
 *
 * Session strategy (see docs/adr/0001-auth-session-strategy.md): the short-lived access token
 * lives only in this module's memory; the long-lived refresh token is an HttpOnly cookie that
 * JavaScript can never read. Nothing secret is written to localStorage or sessionStorage.
 */

const API_PREFIX = "/api/v1";
const CSRF_HEADERS = { "X-Requested-With": "FoodVerseWeb" };

export interface ApiErrorDetail {
  field: string;
  message: string;
}

export class ApiError extends Error {
  status: number;
  code: string;
  details: ApiErrorDetail[] | null;
  requestId: string | null;

  constructor(
    status: number,
    code: string,
    message: string,
    details: ApiErrorDetail[] | null = null,
    requestId: string | null = null,
  ) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.details = details;
    this.requestId = requestId;
  }
}

let accessToken: string | null = null;
let refreshInFlight: Promise<AuthResponse | null> | null = null;
let onSessionLost: (() => void) | null = null;

export function setAccessToken(token: string | null): void {
  accessToken = token;
}

export function setSessionLostHandler(handler: (() => void) | null): void {
  onSessionLost = handler;
}

interface RequestOptions {
  method?: "GET" | "POST" | "PUT";
  body?: unknown;
  /** Attach the access token and refresh once on 401. Auth endpoints pass false. */
  authenticated?: boolean;
}

async function send(path: string, options: RequestOptions, token: string | null): Promise<Response> {
  const headers: Record<string, string> = { ...CSRF_HEADERS };
  if (options.body !== undefined) headers["Content-Type"] = "application/json";
  if (token && options.authenticated !== false) headers["Authorization"] = `Bearer ${token}`;
  return fetch(`${API_PREFIX}${path}`, {
    method: options.method ?? "GET",
    headers,
    credentials: "include",
    body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
  });
}

async function toApiError(response: Response): Promise<ApiError> {
  try {
    const data = (await response.json()) as {
      error?: { code?: string; message?: string; details?: ApiErrorDetail[] | null; request_id?: string | null };
    };
    const err = data.error;
    if (err) {
      return new ApiError(
        response.status,
        err.code ?? "http_error",
        err.message ?? "Request failed.",
        err.details ?? null,
        err.request_id ?? null,
      );
    }
  } catch {
    // fall through: body was not JSON
  }
  return new ApiError(response.status, "http_error", "Request failed.");
}

/** Exchange the refresh cookie for a new access token. Concurrent callers share one request. */
export function refreshSession(): Promise<AuthResponse | null> {
  if (!refreshInFlight) {
    refreshInFlight = (async () => {
      try {
        const response = await send("/auth/refresh", { method: "POST", authenticated: false }, null);
        if (!response.ok) {
          accessToken = null;
          return null;
        }
        const data = (await response.json()) as AuthResponse;
        accessToken = data.access_token;
        return data;
      } catch {
        accessToken = null;
        return null;
      } finally {
        refreshInFlight = null;
      }
    })();
  }
  return refreshInFlight;
}

export async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  let response = await send(path, options, accessToken);

  if (response.status === 401 && options.authenticated !== false) {
    const refreshed = await refreshSession();
    if (!refreshed) {
      onSessionLost?.();
      throw await toApiError(response);
    }
    response = await send(path, options, accessToken);
  }

  if (!response.ok) throw await toApiError(response);
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}
