import pytest
from fastapi.testclient import TestClient

from tests.conftest import USER, auth_headers


@pytest.mark.parametrize(
    "patch",
    [
        {"email": "not-an-email"},
        {"password": "short"},
        {"password": "x" * 129},
        {"display_name": "   "},
        {"display_name": ""},
        {"display_name": "n" * 81},
        {"unexpected": "field"},
    ],
)
def test_register_validation_errors(client: TestClient, patch: dict[str, str]) -> None:
    r = client.post("/api/v1/auth/register", json={**USER, **patch})
    assert r.status_code == 422
    err = r.json()["error"]
    assert err["code"] == "validation_error" and err["details"]


def test_validation_errors_never_echo_the_password(client: TestClient) -> None:
    r = client.post("/api/v1/auth/register", json={**USER, "password": "short-pw"})
    assert r.status_code == 422
    assert "short-pw" not in r.text


def test_register_missing_fields(client: TestClient) -> None:
    assert client.post("/api/v1/auth/register", json={}).status_code == 422


def test_login_validation(client: TestClient) -> None:
    assert (
        client.post("/api/v1/auth/login", json={"email": "bad", "password": "x"}).status_code == 422
    )
    assert (
        client.post("/api/v1/auth/login", json={"email": "a@b.co", "password": ""}).status_code
        == 422
    )


@pytest.mark.parametrize(
    "payload",
    [
        {"unit_system": "stones"},
        {"unit_system": "metric", "dietary_preferences": ["carnivore"]},
        {"unit_system": "metric", "allergies": ["<script>"]},
        {"unit_system": "metric", "allergies": [""]},
        {"unit_system": "metric", "allergies": ["a" * 51]},
        {"unit_system": "metric", "allergies": [f"item{i}" for i in range(21)]},
        {"unit_system": "metric", "role": "admin"},
        {},
    ],
)
def test_preferences_validation(
    client: TestClient, registered: dict[str, str], payload: dict[str, object]
) -> None:
    r = client.put(
        "/api/v1/users/me/preferences", headers=auth_headers(registered["token"]), json=payload
    )
    assert r.status_code == 422, payload


def test_error_responses_have_consistent_shape_and_request_id(client: TestClient) -> None:
    r = client.get("/api/v1/does-not-exist")
    assert r.status_code == 404
    err = r.json()["error"]
    assert set(err) == {"code", "message", "details", "request_id"}
    assert err["code"] == "not_found"
    assert err["request_id"] == r.headers["x-request-id"]


def test_security_headers_are_set(client: TestClient) -> None:
    r = client.get("/api/v1/health")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["x-frame-options"] == "DENY"
    assert r.headers["cache-control"] == "no-store"


def test_preference_options_are_public(client: TestClient) -> None:
    r = client.get("/api/v1/meta/preference-options")
    assert r.status_code == 200
    body = r.json()
    assert "vegan" in body["dietary_preferences"] and "peanut" in body["common_allergens"]
    assert body["unit_systems"] == ["metric", "imperial"]
