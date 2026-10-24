import uuid
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from app.db.session import get_session_factory
from app.models import AnalysisRecord, AnalysisStatus, ModuleKey
from tests.conftest import USER, auth_headers, register_user
from tests.imgs import make_image, upload_files


def _user_id(client: TestClient, token: str) -> uuid.UUID:
    return uuid.UUID(client.get("/api/v1/users/me", headers=auth_headers(token)).json()["id"])


def _seed(
    owner: uuid.UUID, n: int, module: ModuleKey = ModuleKey.FRESHNESS, prefix: str = "Entry"
) -> list[uuid.UUID]:
    """Insert records directly. Test-only data: production code never creates fake history."""
    ids = []
    base = datetime.now(UTC) - timedelta(hours=1)
    with get_session_factory()() as db:
        for i in range(n):
            # explicit, increasing timestamps: rows in one transaction would otherwise tie
            rec = AnalysisRecord(
                owner_id=owner,
                module=module,
                status=AnalysisStatus.COMPLETED,
                title=f"{prefix} {i}",
                summary="s",
                result={"k": i},
                created_at=base + timedelta(seconds=i),
            )
            db.add(rec)
            db.flush()
            ids.append(rec.id)
        db.commit()
    return ids


def test_new_account_has_empty_history_and_zeroed_dashboard(
    client: TestClient, registered: dict[str, str]
) -> None:
    h = auth_headers(registered["token"])
    hist = client.get("/api/v1/history", headers=h).json()
    assert hist == {"items": [], "total": 0, "page": 1, "page_size": 20, "pages": 0}
    dash = client.get("/api/v1/dashboard/summary", headers=h).json()
    assert dash["media"]["count"] == 0 and dash["media"]["total_bytes"] == 0
    assert dash["history"] == {"total": 0, "by_module": {}}
    assert dash["recent"] == []
    assert dash["media"]["quota_bytes"] > 0 and dash["media"]["max_upload_bytes"] > 0


def test_dashboard_reflects_real_data(client: TestClient, registered: dict[str, str]) -> None:
    h = auth_headers(registered["token"])
    owner = _user_id(client, registered["token"])
    up = client.post(
        "/api/v1/media", headers=h, files=upload_files(make_image("PNG"), "a.png", "image/png")
    )
    size = up.json()["size_bytes"]
    _seed(owner, 3, ModuleKey.FRESHNESS)
    _seed(owner, 2, ModuleKey.HYGIENE, prefix="Kitchen")
    dash = client.get("/api/v1/dashboard/summary", headers=h).json()
    assert dash["media"]["count"] == 1 and dash["media"]["total_bytes"] == size
    assert dash["history"]["total"] == 5
    assert dash["history"]["by_module"] == {"freshness": 3, "hygiene": 2}
    assert len(dash["recent"]) == 5
    assert "result" not in dash["recent"][0]


def test_dashboard_recent_is_capped_and_newest_first(
    client: TestClient, registered: dict[str, str]
) -> None:
    owner = _user_id(client, registered["token"])
    _seed(owner, 8)
    recent = client.get(
        "/api/v1/dashboard/summary", headers=auth_headers(registered["token"])
    ).json()["recent"]
    assert len(recent) == 5
    assert recent[0]["title"] == "Entry 7"


def test_dashboard_is_isolated_per_user(client: TestClient, registered: dict[str, str]) -> None:
    owner = _user_id(client, registered["token"])
    _seed(owner, 4)
    bob = register_user(client, "bob@example.com")
    dash = client.get("/api/v1/dashboard/summary", headers=auth_headers(bob)).json()
    assert dash["history"]["total"] == 0 and dash["recent"] == []


def test_modules_are_listed_and_none_claims_to_be_available(
    client: TestClient, registered: dict[str, str]
) -> None:
    mods = client.get("/api/v1/modules", headers=auth_headers(registered["token"])).json()
    assert [m["key"] for m in mods] == [
        "food_recognition",
        "freshness",
        "hygiene",
        "cooking",
        "meal_planning",
    ]
    assert all(m["available"] is False for m in mods)


def test_history_pagination_filter_and_order(
    client: TestClient, registered: dict[str, str]
) -> None:
    h = auth_headers(registered["token"])
    owner = _user_id(client, registered["token"])
    _seed(owner, 7, ModuleKey.FRESHNESS)
    _seed(owner, 3, ModuleKey.COOKING, prefix="Recipe")
    p1 = client.get("/api/v1/history?page=1&page_size=4", headers=h).json()
    p3 = client.get("/api/v1/history?page=3&page_size=4", headers=h).json()
    assert (p1["total"], p1["pages"], len(p1["items"]), len(p3["items"])) == (10, 3, 4, 2)
    only = client.get("/api/v1/history?module=cooking", headers=h).json()
    assert only["total"] == 3 and {i["module"] for i in only["items"]} == {"cooking"}
    beyond = client.get("/api/v1/history?page=99", headers=h).json()
    assert beyond["items"] == [] and beyond["total"] == 10


def test_history_query_validation(client: TestClient, registered: dict[str, str]) -> None:
    h = auth_headers(registered["token"])
    for q in ("page=0", "page_size=0", "page_size=101", "module=nope", "page=abc"):
        r = client.get(f"/api/v1/history?{q}", headers=h)
        assert r.status_code == 422 and r.json()["error"]["code"] == "validation_error", q


def test_history_detail_and_delete_with_ownership(
    client: TestClient, registered: dict[str, str]
) -> None:
    alice = registered["token"]
    bob = register_user(client, "bob@example.com")
    rid = str(_seed(_user_id(client, alice), 1)[0])
    ha, hb = auth_headers(alice), auth_headers(bob)

    assert client.get(f"/api/v1/history/{rid}", headers=ha).json()["result"] == {"k": 0}
    assert client.get(f"/api/v1/history/{rid}", headers=hb).status_code == 404
    assert client.delete(f"/api/v1/history/{rid}", headers=hb).status_code == 404
    assert client.get(f"/api/v1/history/{rid}", headers=ha).status_code == 200
    assert (
        client.delete(
            f"/api/v1/history/{rid}", headers={"Authorization": ha["Authorization"]}
        ).status_code
        == 403
    )
    assert client.delete(f"/api/v1/history/{rid}", headers=ha).status_code == 204
    assert client.get(f"/api/v1/history/{rid}", headers=ha).status_code == 404
    assert client.get("/api/v1/history", headers=hb).json()["total"] == 0


def test_history_requires_authentication(client: TestClient) -> None:
    for path in (
        "/api/v1/history",
        "/api/v1/dashboard/summary",
        "/api/v1/modules",
        f"/api/v1/history/{uuid.uuid4()}",
    ):
        assert client.get(path).status_code == 401, path


def test_deleting_media_keeps_history_but_clears_the_link(
    client: TestClient, registered: dict[str, str]
) -> None:
    h = auth_headers(registered["token"])
    owner = _user_id(client, registered["token"])
    mid = client.post(
        "/api/v1/media", headers=h, files=upload_files(make_image("PNG"), "a.png", "image/png")
    ).json()["id"]
    with get_session_factory()() as db:
        rec = AnalysisRecord(
            owner_id=owner,
            module=ModuleKey.FRESHNESS,
            status=AnalysisStatus.COMPLETED,
            title="With photo",
            media_id=uuid.UUID(mid),
        )
        db.add(rec)
        db.commit()
        rid = rec.id
    assert client.get(f"/api/v1/history/{rid}", headers=h).json()["media_id"] == mid
    client.delete(f"/api/v1/media/{mid}", headers=h)
    assert client.get(f"/api/v1/history/{rid}", headers=h).json()["media_id"] is None


def test_profile_update(client: TestClient, registered: dict[str, str]) -> None:
    h = auth_headers(registered["token"])
    r = client.patch("/api/v1/users/me", headers=h, json={"display_name": "  Asha   K  "})
    assert r.status_code == 200 and r.json()["display_name"] == "Asha K"
    assert client.get("/api/v1/users/me", headers=h).json()["display_name"] == "Asha K"
    for bad in ({"display_name": "  "}, {"display_name": "x" * 81}, {"email": "x@y.co"}, {}):
        assert client.patch("/api/v1/users/me", headers=h, json=bad).status_code == 422
    no_csrf = client.patch(
        "/api/v1/users/me",
        headers={"Authorization": h["Authorization"]},
        json={"display_name": "Z"},
    )
    assert no_csrf.status_code == 403


def test_change_password_revokes_sessions(client: TestClient, registered: dict[str, str]) -> None:
    h = auth_headers(registered["token"])
    wrong = client.post(
        "/api/v1/users/me/password",
        headers=h,
        json={"current_password": "nope-nope-nope", "new_password": "a brand new passphrase"},
    )
    assert wrong.status_code == 400 and wrong.json()["error"]["code"] == "invalid_current_password"
    same = client.post(
        "/api/v1/users/me/password",
        headers=h,
        json={"current_password": USER["password"], "new_password": USER["password"]},
    )
    assert same.status_code == 400 and same.json()["error"]["code"] == "password_unchanged"
    short = client.post(
        "/api/v1/users/me/password",
        headers=h,
        json={"current_password": USER["password"], "new_password": "short"},
    )
    assert short.status_code == 422

    ok = client.post(
        "/api/v1/users/me/password",
        headers=h,
        json={"current_password": USER["password"], "new_password": "a brand new passphrase"},
    )
    assert ok.status_code == 204
    assert (
        client.post(
            "/api/v1/auth/refresh", headers={"X-Requested-With": "FoodVerseWeb"}
        ).status_code
        == 401
    )
    old = client.post(
        "/api/v1/auth/login", json={"email": "asha@example.com", "password": USER["password"]}
    )
    new = client.post(
        "/api/v1/auth/login",
        json={"email": "asha@example.com", "password": "a brand new passphrase"},
    )
    assert old.status_code == 401 and new.status_code == 200
