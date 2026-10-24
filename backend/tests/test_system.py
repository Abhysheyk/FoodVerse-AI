import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.ai.ollama import OllamaClient
from app.core.config import Settings, get_settings
from app.db.session import get_session_factory
from tests.conftest import auth_headers


def test_health_is_ok(client: TestClient) -> None:
    r = client.get("/api/v1/health")
    assert r.status_code == 200 and r.json()["status"] == "ok"


def test_ready_checks_database_and_migrations(client: TestClient) -> None:
    r = client.get("/api/v1/ready")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "checks": {"database": "ok", "migrations": "ok"}}


def test_ready_reports_unavailable_when_migrations_are_behind(client: TestClient) -> None:
    with get_session_factory()() as db:
        original = db.execute(text("SELECT version_num FROM alembic_version")).scalar()
        try:
            db.execute(text("UPDATE alembic_version SET version_num = 'stale'"))
            db.commit()
            r = client.get("/api/v1/ready")
        finally:
            db.execute(text("UPDATE alembic_version SET version_num = :v"), {"v": original})
            db.commit()
    assert r.status_code == 503
    assert r.json()["checks"]["migrations"] == "not_up_to_date"


def test_cors_allows_configured_origin_only(client: TestClient) -> None:
    allowed = get_settings().cors_origins[0]
    ok = client.options(
        "/api/v1/auth/login",
        headers={"Origin": allowed, "Access-Control-Request-Method": "POST"},
    )
    assert ok.headers["access-control-allow-origin"] == allowed
    assert ok.headers["access-control-allow-credentials"] == "true"
    bad = client.options(
        "/api/v1/auth/login",
        headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "POST"},
    )
    assert "access-control-allow-origin" not in bad.headers


def test_ai_status_when_ollama_disabled(client: TestClient, registered: dict[str, str]) -> None:
    r = client.get("/api/v1/ai/status", headers=auth_headers(registered["token"]))
    assert r.status_code == 200
    body = r.json()
    assert body["ollama"]["enabled"] is False and body["ollama"]["reachable"] is None
    assert body["fallback_policy"] == "none" and body["external_providers_allowed"] is False


def _settings(**over: object) -> Settings:
    base = {
        "database_url": "postgresql://u:p@localhost/db_test",
        "jwt_secret_key": "k" * 40,
        "ollama_enabled": True,
        "ollama_text_model": "llama3.2:3b",
        "ollama_vision_model": "vision-model",
    }
    return Settings(_env_file=None, **{**base, **over})  # type: ignore[arg-type]


def test_ollama_client_reports_installed_models() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/tags"
        return httpx.Response(
            200, json={"models": [{"name": "llama3.2:3b"}, {"name": "other:latest"}]}
        )

    status = OllamaClient(_settings(), transport=httpx.MockTransport(handler)).status().ollama
    assert status.reachable is True
    assert status.text_model.installed is True
    assert status.vision_model.installed is False  # configured but not pulled; nothing downloaded


def test_ollama_client_unreachable_is_reported_not_raised() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    status = OllamaClient(_settings(), transport=httpx.MockTransport(handler)).status().ollama
    assert status.reachable is False and status.error
    assert status.text_model.installed is None


def test_config_rejects_bad_values() -> None:
    with pytest.raises(ValueError):
        _settings(database_url="mysql://x")
    with pytest.raises(ValueError):
        _settings(cors_allowed_origins="*")
    with pytest.raises(ValueError):
        _settings(jwt_secret_key="short")
    with pytest.raises(ValueError):
        _settings(app_env="production", cookie_secure=False)
    with pytest.raises(ValueError):
        _settings(app_env="production", jwt_secret_key="replace-with-a-long-random-secret-value")
