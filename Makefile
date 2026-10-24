# Convenience targets for Linux/macOS/WSL. Windows users: run the commands in README.md.
BACKEND := backend
PY := $(BACKEND)/.venv/bin

setup:
	python3 -m venv $(BACKEND)/.venv
	$(PY)/pip install -r $(BACKEND)/requirements.txt -r $(BACKEND)/requirements-dev.txt
	cd frontend && npm ci

migrate:
	cd $(BACKEND) && .venv/bin/alembic upgrade head

dev-backend:
	cd $(BACKEND) && .venv/bin/uvicorn app.main:app --reload --port 8000

dev-frontend:
	cd frontend && npm run dev

test:
	cd $(BACKEND) && .venv/bin/pytest -q
	cd frontend && npm test

lint:
	cd $(BACKEND) && .venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/mypy app tests
	cd frontend && npm run lint && npm run typecheck

# Requires uv (https://docs.astral.sh/uv/).
lock:
	cd $(BACKEND) && uv pip compile --universal --generate-hashes --python-version 3.11 --no-header -o requirements.txt requirements.in
	cd $(BACKEND) && uv pip compile --universal --generate-hashes --python-version 3.11 --no-header -o requirements-dev.txt requirements-dev.in
