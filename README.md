# FoodVerse AI

Multimodal food intelligence app: React + TypeScript frontend, FastAPI + PostgreSQL backend,
local-first AI (optional Ollama; no paid API is ever required or used as a silent fallback).

**Current status: Phase 1 (foundation) only.** Accounts, sign-in, preferences (units, dietary
preferences, allergies), health checks and an AI-status view exist. Food recognition, freshness,
hygiene, cooking, meal planning, audio and video are **not built yet**. See
`FOODVERSE_IMPLEMENTATION_PLAN.md`. The IFCT nutrition table is intentionally empty for now.

## Layout
```
backend/   FastAPI app (app/api, services, repositories, models, schemas, ai, core), alembic/, tests/
frontend/  React + TS (Vite): src/api, auth, pages, components, test
docs/adr/  Architecture decision records
```

## Prerequisites
Python 3.11+, Node 20+, PostgreSQL 14+ (locally installed). Ollama is optional in Phase 1.

## 1. Database (one time)
In `psql` as a superuser (choose your own password):
```sql
CREATE USER foodverse WITH PASSWORD 'CHANGE_ME' CREATEDB;
CREATE DATABASE foodverse_dev  OWNER foodverse;
CREATE DATABASE foodverse_test OWNER foodverse;  -- tests only; they truncate tables here
```

## 2. Backend
```bash
cd backend
python -m venv .venv
source .venv/bin/activate            # Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements.txt -r requirements-dev.txt
cp .env.example .env                 # Windows: copy .env.example .env
# edit .env: set DATABASE_URL password and a real JWT_SECRET_KEY
alembic upgrade head                 # applies migrations (never drops data)
uvicorn app.main:app --reload --port 8000
```
API docs: http://localhost:8000/api/docs. Liveness `GET /api/v1/health`, readiness
`GET /api/v1/ready` (checks database and that migrations are current).

## 3. Frontend
```bash
cd frontend
npm ci
npm run dev                          # http://localhost:5173, proxies /api to :8000
```
Open http://localhost:5173, register, then set your preferences.

## Tests and checks
```bash
# backend (set TEST_DATABASE_URL to the *_test database; PowerShell: $env:TEST_DATABASE_URL="...")
cd backend
export TEST_DATABASE_URL=postgresql+psycopg://foodverse:CHANGE_ME@localhost:5432/foodverse_test
pytest -q && ruff check . && ruff format --check . && mypy app tests

# frontend
cd frontend
npm test && npm run lint && npm run typecheck && npm run build
```
Backend tests run the real Alembic migrations on the test database and never touch the dev one.
`make setup | migrate | dev-backend | dev-frontend | test | lint | lock` wraps these on
Linux/macOS/WSL.

## Dependencies
`backend/requirements.in` / `requirements-dev.in` are the editable lists; `requirements*.txt`
are hash-pinned locks (regenerate with `make lock`, needs `uv`). Frontend is locked by
`package-lock.json`.

## API (v1)
| Method | Path | Auth |
|---|---|---|
| POST | /auth/register, /auth/login | none |
| POST | /auth/refresh, /auth/logout | refresh cookie + `X-Requested-With` header |
| GET | /users/me | bearer |
| GET, PUT | /users/me/preferences | bearer (PUT also needs the header) |
| GET | /meta/preference-options | none |
| GET | /ai/status | bearer |
| GET | /health, /ready | none |

Errors always look like `{"error": {"code", "message", "details", "request_id"}}`.

## Security notes
Session design and its limits are in `docs/adr/0001-auth-session-strategy.md`: short-lived
in-memory access token, HttpOnly rotating refresh cookie, Argon2id passwords, no tokens in web
storage. Request bodies and passwords are never logged. Not yet done: rate limiting, email
verification, password reset, CSP (planned for Phase 8).

## Optional local AI
Set `OLLAMA_ENABLED=true` and model names in `backend/.env`. Phase 1 only *reports* whether
Ollama is reachable and the models are installed (Dashboard). It never downloads models; pull
them yourself (`ollama pull <name>`). Expect slow CPU-only inference on 8 GB machines.

## Disclaimer
Allergy and diet settings are user-declared. This app is not medical advice and not a substitute
for qualified professionals or official food-safety inspection.
