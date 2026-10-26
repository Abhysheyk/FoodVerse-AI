# FoodVerse AI – Implementation Plan (Phase 0 audit, greenfield)

## 1. Audit result
- Repository `Abhysheyk/FoodVerse-AI`: could not be accessed from this environment (GitHub not linked). Owner states the project is **not started and empty**. Nothing was inspected in it; no existing work to preserve.
- Spec sources reviewed: 2 slides (problem, solution, core functions, scope, challenges, tech list) and the architecture diagram (User Input -> FastAPI -> AI Models -> 4 outputs; DB/files storage; React frontend).
- Existing: nothing. Missing: everything (frontend, backend, DB, auth, env config, tests, deployment).
- Duplicates / security issues / broken flows / risky dependencies: none to report (no code).

## 2. Constraints
- Dev machine: 8 GB RAM, Ryzen 3 7320U, integrated GPU only (no CUDA). Local PostgreSQL (version not yet provided).
- Local-first, no paid APIs required, no silent paid fallback. No automatic model downloads.
- Slide mentions PyTorch/OpenCV/Meta LLaMA; plan uses Ollama for LLaMA-family text and small VLMs, OpenCV only for deterministic image checks (blur, brightness, size). PyTorch is **not** required in phase 1-3 (heavy install on 8 GB); revisit only if needed.

## 3. Architecture
Monorepo:
```
foodverse-ai/
  backend/  app/{api,schemas,services,domain,ai,repositories,models,media,core}  alembic/  tests/
  frontend/ src/{api,components,features,pages,hooks,types}
  docs/adr/  .env.example  docker-compose.yml (optional, postgres only)  README.md
```
- Backend: FastAPI, SQLAlchemy 2.x, Alembic, Pydantic v2, PostgreSQL. Layers: api -> services -> domain/repositories; AI only via `ai/` provider interfaces.
- Frontend: React + TypeScript (Vite), typed API client, React Router, accessible responsive UI.
- Auth: email+password, Argon2/bcrypt hashing, short-lived JWT, per-user data isolation (needed for allergies, plans, history).
- Media: size/type allow-list, magic-byte check, random filenames, storage outside web root, EXIF stripped, videos sampled to frames (ffmpeg, must be installed), audio via local transcription.
- Jobs: FastAPI BackgroundTasks first (slow CPU inference); status polling endpoint. No Celery/Redis unless proven necessary.

## 4. AI strategy
- Interfaces: `TextProvider`, `VisionProvider`, `TranscriptionProvider`. Adapters: Ollama (default), optional external adapters (off by default, explicit config + UI disclosure), Mock (tests only; production refuses to start with mock).
- Health check endpoint reports which providers/models are available. If none: features return a clear "model unavailable" state with setup steps; no fabricated output.
- Suggested models (user must pull manually, sizes to verify at setup): a small Ollama VLM (e.g. a 2-4B vision model) and a small LLaMA-family text model. Transcription: faster-whisper tiny/base (CPU). Exact choices are config values, confirmed with user before documenting as tested.
- Expect slow CPU inference (tens of seconds per image). UI shows progress; timeouts configurable.
- Trust rules: model output = observations only (labelled "model-generated"); nutrition math is deterministic from the data table. No numeric "confidence" unless a model actually returns a calibrated score; otherwise show qualitative uncertainty (low/medium/high derived from image-quality checks and model self-report, labelled as such). User confirms food identity and portion before nutrition is computed/saved. Freshness/hygiene = advisory, with disclaimer and "cannot determine" as a valid outcome.

## 5. Nutrition data (IFCT)
- Source: Indian Food Composition Tables (ICMR-NIN, IFCT 2017). **Blocker: I will not type values from memory.** Need either (a) a dataset file you supply/licence-check, or (b) approval for me to import from a source you name. Import script + provenance table (source, edition, per-100 g basis, licence) are built; the table stays empty until real data is loaded.
- Foods not in IFCT: reported as "no verified data", user may enter values manually (flagged user-entered). No guessing.
- Allergen/diet tags: user-maintained plus keyword rules; always shown as "verify on label".

## 6. Phases
| # | Scope | Acceptance criteria |
|---|---|---|
| 0 | This plan | Plan approved by owner |
| 1 | Foundation: repo scaffold, config/.env.example, DB + Alembic baseline, auth, user profile (allergies/diet), Ollama status check, scripts, frontend shell. **Moved to Phase 2:** upload pipeline and provider interfaces (no consumer yet) | migrations apply on clean DB; register/login works; unauthorised access rejected; bad uploads rejected; lint/type/tests/build pass |
| 2 | **Shared shell + media (delivered):** app layout, dashboard, settings, history views, validated image uploads, storage abstraction, history pagination. *Food recognition + IFCT import moves to Phase 3 and later phases shift by one.* | uploads validated/isolated; dashboard uses real data; no fake records |
| 3 | **Food recognition + nutrition (delivered, see ADR 0003):** photo/manual entry, editable detections, USDA/OFF/local sources, deterministic totals, meal log CRUD. Barcode UI and IFCT data (needs your file) remain open. *(Freshness/spoilage moves to Phase 4; later phases shift by one.)* | model output validated; no invented values; ownership enforced; tests pass |
| 4 | Freshness/spoilage | Visible-sign observations, advisory wording, low-quality-image warnings, history |
| 5 | Hygiene monitoring | Checklist-based visible-concern report, disclaimer, no compliance claims, history |
| 6 | Cooking assistant + recipes | Recipe from ingredients/text respecting allergies; allergen warning tests |
| 7 | Meal planning, tracking, grocery lists | Plan generation from profile, daily totals from deterministic maths, grocery list from plan |
| 8 | Audio + video inputs | Audio -> transcript -> routed to features; video -> sampled frames; limits enforced |
| 9 | Hardening + docs + deployment | Security review, rate limits, README/API docs, Docker/run scripts, backup notes, full test run |

## 7. Setup requirements (owner machine)
Python 3.11+, Node 20+, PostgreSQL (version?), Ollama + manually pulled models, ffmpeg (video/audio), ~8 GB free disk for models. Nothing is downloaded automatically.

## 8. Risks
CPU-only inference is slow and may exhaust 8 GB RAM alongside Postgres; VLM accuracy on Indian dishes unproven; IFCT licence/format uncertainty; freshness/hygiene accuracy limited (slide-listed challenge); scope is large for one pass.

## 9. Open questions for owner
IFCT data file/source; Postgres version and DB credentials (kept in `.env`); preferred package managers; confirm phased delivery vs one-shot build.
