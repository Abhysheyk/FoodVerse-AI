from datetime import UTC, datetime, timedelta

import jwt
from fastapi.testclient import TestClient
from sqlalchemy import select, text

from app.core.config import get_settings
from app.db.session import get_session_factory
from app.models import RefreshToken, User
from tests.conftest import CSRF, USER, auth_headers


def test_register_returns_token_and_sets_http_only_refresh_cookie(client: TestClient) -> None:
    r = client.post("/api/v1/auth/register", json=USER)
    assert r.status_code == 201
    body = r.json()
    assert body["token_type"] == "bearer" and body["access_token"]
    assert body["user"]["email"] == "asha@example.com"  # normalised to lowercase
    assert "password" not in str(body).lower().replace("password_", "")
    assert "password_hash" not in body["user"]
    cookie = r.headers["set-cookie"]
    assert "fv_refresh=" in cookie and "HttpOnly" in cookie and "Path=/api/v1/auth" in cookie


def test_password_is_stored_as_argon2id_hash(
    client: TestClient, registered: dict[str, str]
) -> None:
    with get_session_factory()() as db:
        user = db.scalar(select(User))
        assert user is not None
        assert user.password_hash.startswith("$argon2id$")
        assert USER["password"] not in user.password_hash
        raw = client.cookies.get("fv_refresh")
        stored = db.scalars(select(RefreshToken.token_hash)).all()
        assert raw and raw not in stored  # only a hash of the refresh token is stored


def test_register_creates_default_preferences(
    client: TestClient, registered: dict[str, str]
) -> None:
    r = client.get("/api/v1/users/me/preferences", headers=auth_headers(registered["token"]))
    assert r.status_code == 200
    assert r.json()["unit_system"] == "metric"
    assert r.json()["allergies"] == [] and r.json()["dietary_preferences"] == []


def test_duplicate_email_is_rejected_case_insensitively(
    client: TestClient, registered: dict[str, str]
) -> None:
    r = client.post("/api/v1/auth/register", json={**USER, "email": "ASHA@example.COM"})
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "email_taken"


def test_login_success(client: TestClient, registered: dict[str, str]) -> None:
    r = client.post(
        "/api/v1/auth/login", json={"email": "asha@example.com", "password": USER["password"]}
    )
    assert r.status_code == 200
    assert r.json()["user"]["display_name"] == "Asha"


def test_login_failures_are_indistinguishable(
    client: TestClient, registered: dict[str, str]
) -> None:
    wrong_pw = client.post(
        "/api/v1/auth/login", json={"email": "asha@example.com", "password": "nope-nope-nope"}
    )
    no_user = client.post(
        "/api/v1/auth/login", json={"email": "ghost@example.com", "password": "nope-nope-nope"}
    )
    assert wrong_pw.status_code == no_user.status_code == 401
    assert (
        wrong_pw.json()["error"]["code"] == no_user.json()["error"]["code"] == "invalid_credentials"
    )
    assert wrong_pw.json()["error"]["message"] == no_user.json()["error"]["message"]


def test_inactive_user_cannot_login(client: TestClient, registered: dict[str, str]) -> None:
    with get_session_factory()() as db:
        db.execute(text("UPDATE users SET is_active = false"))
        db.commit()
    r = client.post(
        "/api/v1/auth/login", json={"email": "asha@example.com", "password": USER["password"]}
    )
    assert r.status_code == 401


def test_refresh_requires_csrf_header(client: TestClient, registered: dict[str, str]) -> None:
    r = client.post("/api/v1/auth/refresh")
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "csrf_check_failed"


def test_refresh_rotates_token_and_reuse_revokes_all_sessions(
    client: TestClient, registered: dict[str, str]
) -> None:
    old = client.cookies.get("fv_refresh")
    assert old
    r = client.post("/api/v1/auth/refresh", headers=CSRF)
    assert r.status_code == 200
    new = client.cookies.get("fv_refresh")
    assert new and new != old

    # Replaying the old (now revoked) token is treated as theft: all sessions are revoked.
    client.cookies.set("fv_refresh", old, path="/api/v1/auth")
    replay = client.post("/api/v1/auth/refresh", headers=CSRF)
    assert replay.status_code == 401
    assert replay.json()["error"]["code"] == "invalid_refresh"

    client.cookies.set("fv_refresh", new, path="/api/v1/auth")
    assert client.post("/api/v1/auth/refresh", headers=CSRF).status_code == 401


def test_refresh_without_cookie_is_unauthorised(client: TestClient) -> None:
    r = client.post("/api/v1/auth/refresh", headers=CSRF)
    assert r.status_code == 401


def test_logout_revokes_refresh_token_and_clears_cookie(
    client: TestClient, registered: dict[str, str]
) -> None:
    token = client.cookies.get("fv_refresh")
    assert token
    r = client.post("/api/v1/auth/logout", headers=CSRF)
    assert r.status_code == 204
    assert "fv_refresh=" in r.headers["set-cookie"] and "Max-Age=0" in r.headers["set-cookie"]
    client.cookies.set("fv_refresh", token, path="/api/v1/auth")
    assert client.post("/api/v1/auth/refresh", headers=CSRF).status_code == 401


def test_logout_requires_csrf_header(client: TestClient, registered: dict[str, str]) -> None:
    assert client.post("/api/v1/auth/logout").status_code == 403


def test_logout_without_session_is_harmless(client: TestClient) -> None:
    assert client.post("/api/v1/auth/logout", headers=CSRF).status_code == 204


def _token(
    sub: str, *, secret: str | None = None, expires_in: int = 300, typ: str = "access"
) -> str:
    now = datetime.now(UTC)
    payload = {"sub": sub, "type": typ, "iat": now, "exp": now + timedelta(seconds=expires_in)}
    return jwt.encode(payload, secret or get_settings().jwt_secret_key, algorithm="HS256")


def test_me_with_valid_token(client: TestClient, registered: dict[str, str]) -> None:
    r = client.get("/api/v1/users/me", headers=auth_headers(registered["token"]))
    assert r.status_code == 200
    assert r.json()["email"] == "asha@example.com"
    assert "password_hash" not in r.json()


def test_rejects_expired_forged_and_wrong_type_tokens(
    client: TestClient, registered: dict[str, str]
) -> None:
    me = client.get("/api/v1/users/me", headers=auth_headers(registered["token"])).json()
    bad = [
        _token(me["id"], expires_in=-10),
        _token(me["id"], secret="x" * 40),
        _token(me["id"], typ="refresh"),
        _token("not-a-uuid"),
        "garbage.token.value",
    ]
    for tok in bad:
        r = client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {tok}"})
        assert r.status_code == 401, tok
        assert r.json()["error"]["code"] == "invalid_token"


def test_token_for_deactivated_user_is_rejected(
    client: TestClient, registered: dict[str, str]
) -> None:
    with get_session_factory()() as db:
        db.execute(text("UPDATE users SET is_active = false"))
        db.commit()
    r = client.get("/api/v1/users/me", headers=auth_headers(registered["token"]))
    assert r.status_code == 401
