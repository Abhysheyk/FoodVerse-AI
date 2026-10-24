"""Test setup.

Tests run against a dedicated PostgreSQL database (TEST_DATABASE_URL) whose name must contain
"test". The schema is created by running the real Alembic migrations, so migrations are
exercised on every run. Tables are emptied between tests; the development database is never
touched.
"""

import os
from collections.abc import Iterator

import pytest

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
if not TEST_DATABASE_URL:
    raise RuntimeError("Set TEST_DATABASE_URL to a dedicated test database (see README).")
if "test" not in TEST_DATABASE_URL.rsplit("/", 1)[-1]:
    raise RuntimeError("TEST_DATABASE_URL database name must contain 'test'.")

os.environ["APP_ENV"] = "test"
os.environ["DATABASE_URL"] = TEST_DATABASE_URL
os.environ.setdefault("JWT_SECRET_KEY", "test-only-secret-key-0123456789-abcdefghij")
os.environ["COOKIE_SECURE"] = "false"
os.environ["COOKIE_SAMESITE"] = "lax"
os.environ["OLLAMA_ENABLED"] = "false"

from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from alembic import command  # noqa: E402
from app.core.config import BACKEND_DIR, get_settings  # noqa: E402
from app.db.session import get_engine  # noqa: E402
from app.main import create_app  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _migrated_database() -> Iterator[None]:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    command.upgrade(cfg, "head")
    yield


@pytest.fixture(autouse=True)
def _clean_tables(_migrated_database: None) -> Iterator[None]:
    yield
    with get_engine().begin() as conn:
        conn.execute(text("TRUNCATE TABLE refresh_tokens, user_preferences, users CASCADE"))


@pytest.fixture
def client() -> Iterator[TestClient]:
    app = create_app(get_settings())
    with TestClient(app, base_url="http://localhost") as c:
        yield c


CSRF = {"X-Requested-With": "FoodVerseWeb"}
USER = {"email": "Asha@Example.com", "password": "correct horse battery", "display_name": "Asha"}


def auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", **CSRF}


@pytest.fixture
def registered(client: TestClient) -> dict[str, str]:
    """Register USER and return {'token': ..., 'email': ...}."""
    r = client.post("/api/v1/auth/register", json=USER)
    assert r.status_code == 201, r.text
    return {"token": r.json()["access_token"], "email": r.json()["user"]["email"]}
