"""Test setup.

Tests run against a dedicated PostgreSQL database (TEST_DATABASE_URL) whose name must contain
"test". The schema is created by running the real Alembic migrations, so migrations are
exercised on every run. Tables are emptied between tests; the development database is never
touched.
"""

import os
import shutil
import tempfile
from collections.abc import Callable, Iterator

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
_MEDIA_DIR = tempfile.mkdtemp(prefix="foodverse-test-media-")
os.environ["MEDIA_ROOT"] = _MEDIA_DIR

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
def _fresh_rate_limits() -> Iterator[None]:
    from app.core.limits import reset_limiters

    reset_limiters()
    yield


@pytest.fixture(autouse=True)
def _clean_tables(_migrated_database: None) -> Iterator[None]:
    yield
    with get_engine().begin() as conn:
        conn.execute(
            text(
                "TRUNCATE TABLE meal_logs, reference_foods, analysis_records, media_assets, "
                "refresh_tokens, user_preferences, users CASCADE"
            )
        )
    shutil.rmtree(_MEDIA_DIR, ignore_errors=True)
    os.makedirs(_MEDIA_DIR, exist_ok=True)


@pytest.fixture
def client() -> Iterator[TestClient]:
    app = create_app(get_settings())
    with TestClient(app, base_url="http://localhost") as c:
        yield c


@pytest.fixture
def make_client() -> Iterator[Callable[..., TestClient]]:
    """Build a client whose settings are overridden (e.g. tiny upload limits)."""
    opened: list[TestClient] = []

    def factory(**overrides: object) -> TestClient:
        settings = get_settings().model_copy(update=overrides)
        app = create_app(settings)
        app.dependency_overrides[get_settings] = lambda: settings
        tc = TestClient(app, base_url="http://localhost")
        tc.__enter__()
        opened.append(tc)
        return tc

    yield factory
    for tc in opened:
        tc.__exit__(None, None, None)


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


def register_user(client: TestClient, email: str, name: str = "Test") -> str:
    """Register another account on this client and return its access token."""
    r = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "correct horse battery", "display_name": name},
    )
    assert r.status_code == 201, r.text
    return str(r.json()["access_token"])
