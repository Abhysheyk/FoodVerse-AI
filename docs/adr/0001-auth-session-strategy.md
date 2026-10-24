# ADR 0001: Authentication and session strategy

Status: accepted (Phase 1)

## Decision
- **Access token**: signed JWT (HS256), 15 minutes, held **only in browser memory** and sent as
  `Authorization: Bearer`. It is never written to localStorage/sessionStorage.
- **Refresh token**: random 48-byte opaque value in an **HttpOnly, SameSite=Strict, Secure**
  cookie (`fv_refresh`), scoped to `Path=/api/v1/auth`, so the browser sends it only to the auth
  endpoints. 14 days. Only its SHA-256 hash is stored (`refresh_tokens`).
- **Rotation and reuse detection**: every refresh revokes the old token and issues a new one.
  Presenting an already-used token revokes all of that user's refresh tokens.
- **Page reload**: the app calls `POST /auth/refresh` on start to restore the session.
- **Logout**: revokes the presented refresh token and clears the cookie.
- **Passwords**: Argon2id (argon2-cffi defaults), rehash on login when parameters change.
  Login runs a dummy hash for unknown emails and returns one error for all failures.
- **CSRF**: cookie-authenticated endpoints (`refresh`, `logout`) require the custom header
  `X-Requested-With: FoodVerseWeb`. Foreign origins cannot send it without a CORS preflight,
  which the exact-origin allow-list rejects. SameSite=Strict is a second layer. Data endpoints
  use the bearer header, which the cookie cannot satisfy.
- **Development**: Vite proxies `/api` to FastAPI so the cookie is same-origin.

## Why not localStorage JWTs / server sessions
localStorage tokens are readable by any injected script and live for their whole lifetime.
Pure server sessions would work, but the short-lived bearer keeps data endpoints stateless and
leaves room for non-browser clients later.

## Known limitations
- An access token cannot be revoked before it expires (max 15 minutes).
- XSS could still call the API while a page is open; a CSP and dependency hygiene are needed
  (Phase 8). Memory-only storage limits theft, not misuse.
- No rate limiting or lockout yet (Phase 8). Registration reveals whether an email exists (409).
- No email verification or password reset yet.
- No "sign out everywhere" control in the UI (reuse detection does it automatically).
- Expired/revoked refresh rows are not purged yet.
