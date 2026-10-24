from fastapi.testclient import TestClient

from tests.conftest import CSRF, USER, auth_headers

PROTECTED_GET = ["/api/v1/users/me", "/api/v1/users/me/preferences", "/api/v1/ai/status"]


def test_protected_routes_require_authentication(client: TestClient) -> None:
    for path in PROTECTED_GET:
        r = client.get(path)
        assert r.status_code == 401, path
        assert r.json()["error"]["code"] == "not_authenticated"
        assert r.headers["www-authenticate"] == "Bearer"
    r = client.put("/api/v1/users/me/preferences", headers=CSRF, json={"unit_system": "metric"})
    assert r.status_code == 401


def test_refresh_cookie_alone_does_not_authenticate_data_routes(
    client: TestClient, registered: dict[str, str]
) -> None:
    assert client.cookies.get("fv_refresh")
    assert client.get("/api/v1/users/me").status_code == 401


def test_preference_update_requires_csrf_header(
    client: TestClient, registered: dict[str, str]
) -> None:
    r = client.put(
        "/api/v1/users/me/preferences",
        headers={"Authorization": f"Bearer {registered['token']}"},
        json={"unit_system": "metric"},
    )
    assert r.status_code == 403


def test_preferences_round_trip_and_normalisation(
    client: TestClient, registered: dict[str, str]
) -> None:
    h = auth_headers(registered["token"])
    r = client.put(
        "/api/v1/users/me/preferences",
        headers=h,
        json={
            "unit_system": "imperial",
            "dietary_preferences": ["vegan", "vegan", "gluten_free"],
            "allergies": ["  Peanut ", "peanut", "Tree   Nut"],
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["unit_system"] == "imperial"
    assert body["dietary_preferences"] == ["vegan", "gluten_free"]
    assert body["allergies"] == ["peanut", "tree nut"]
    again = client.get("/api/v1/users/me/preferences", headers=h).json()
    assert again["allergies"] == ["peanut", "tree nut"]


def test_users_cannot_see_each_others_preferences(
    client: TestClient, registered: dict[str, str]
) -> None:
    client.put(
        "/api/v1/users/me/preferences",
        headers=auth_headers(registered["token"]),
        json={"unit_system": "metric", "allergies": ["shellfish"]},
    )
    other = client.post(
        "/api/v1/auth/register",
        json={**USER, "email": "ravi@example.com", "display_name": "Ravi"},
    ).json()["access_token"]
    mine = client.get("/api/v1/users/me/preferences", headers=auth_headers(other)).json()
    assert mine["allergies"] == []
    assert (
        client.get("/api/v1/users/me", headers=auth_headers(other)).json()["email"]
        == "ravi@example.com"
    )
