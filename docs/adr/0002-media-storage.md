# ADR 0002: Media upload and storage

Status: accepted (Phase 2)

## Decisions
- **Images only for now** (JPEG, PNG, WebP). Audio/video are recognised by extension so the
  error says "not enabled yet", but are never accepted until Phase 7 adds their own signature
  checks, decoders and duration probing.
- **Nothing the client sends is trusted.** The file signature (magic bytes) decides the format;
  the extension and declared Content-Type must both agree with it or the upload is rejected.
  The filename is reduced to a display label and is never used in a path.
- **Re-encode, don't store the original.** Pillow fully decodes the image (corrupt or truncated
  files fail), applies EXIF orientation, then re-encodes. EXIF/GPS data and any appended or
  polyglot payload are dropped. Dimensions are checked from the header before decoding
  (`MAX_IMAGE_PIXELS`) to stop decompression bombs.
- **Size limits are enforced while streaming**: a body-size middleware rejects by
  Content-Length up front and counts bytes as they arrive, so a lying or chunked client cannot
  fill memory or temp disk. Per-user quota (`USER_MEDIA_QUOTA_BYTES`) bounds total storage.
- **Storage names are server-generated** (`ab/<uuid>.<ext>`); `LocalStorage` re-validates each
  key against a strict pattern and checks the resolved path stays under its root. Writes are
  atomic (temp file + rename), directories 0700, files 0600.
- **Location**: `MEDIA_ROOT` (default `~/.foodverse/media`) is outside the repository and is
  never served statically. Files are only reachable through the API.
- **Ownership**: every read, download, metadata fetch and delete goes through
  `get_owned_or_404`. Another user's or a missing id returns the same 404.
- **Delivery**: `GET /media/{id}/content` requires the bearer token, so the UI fetches bytes
  with `fetch` and shows them via object URLs. Responses carry the detected content type,
  `nosniff`, `Cache-Control: private, no-store` and a sandboxing CSP.
- **Abstraction**: services depend on the `StorageBackend` protocol (put/open/delete/exists).
  An S3-compatible backend can implement it later without touching routes or services.
- **Metadata** (`media_assets`): owner, kind, content type, storage key, size, SHA-256,
  width/height, duration (null for images), display name, created time.
- **History** (`analysis_records`): module, status, title, optional media link
  (`ON DELETE SET NULL`), JSON result. No code creates records yet; nothing is seeded.

## Known limitations
- Deleting a user row cascades to `media_assets` but does not delete files (no account
  deletion feature yet). A cleanup job/endpoint is needed when that ships.
- If the process dies between the file write and the database commit, an orphan file can remain
  (normal failures are cleaned up). A periodic orphan sweep is not implemented.
- No antivirus scanning; re-encoding is the mitigation for images.
- Upload progress is not shown (plain `fetch`).
