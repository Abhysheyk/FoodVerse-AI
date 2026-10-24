import os
from pathlib import Path

from fastapi.testclient import TestClient

from tests.conftest import auth_headers, register_user
from tests.imgs import make_image, upload_files

MEDIA_ROOT = Path(os.environ["MEDIA_ROOT"])


def _setup(client: TestClient, registered: dict[str, str]) -> tuple[str, str, str]:
    alice = registered["token"]
    bob = register_user(client, "bob@example.com", "Bob")
    r = client.post(
        "/api/v1/media",
        headers=auth_headers(alice),
        files=upload_files(make_image("PNG"), "private.png", "image/png"),
    )
    assert r.status_code == 201
    return alice, bob, r.json()["id"]


def test_other_users_cannot_read_metadata_content_or_delete(
    client: TestClient, registered: dict[str, str]
) -> None:
    alice, bob, mid = _setup(client, registered)
    hb = auth_headers(bob)
    for path in (
        f"/api/v1/media/{mid}",
        f"/api/v1/media/{mid}/content",
        f"/api/v1/media/{mid}/content?download=true",
    ):
        r = client.get(path, headers=hb)
        assert r.status_code == 404 and r.json()["error"]["code"] == "media_not_found", path
    assert client.delete(f"/api/v1/media/{mid}", headers=hb).status_code == 404
    # ...and the owner is unaffected
    assert (
        client.get(f"/api/v1/media/{mid}/content", headers=auth_headers(alice)).status_code == 200
    )
    assert len([p for p in MEDIA_ROOT.rglob("*") if p.is_file()]) == 1


def test_missing_and_foreign_ids_are_indistinguishable(
    client: TestClient, registered: dict[str, str]
) -> None:
    _, bob, mid = _setup(client, registered)
    foreign = client.get(f"/api/v1/media/{mid}", headers=auth_headers(bob))
    missing = client.get(
        "/api/v1/media/00000000-0000-4000-8000-000000000000", headers=auth_headers(bob)
    )
    assert foreign.status_code == missing.status_code == 404
    assert foreign.json()["error"]["message"] == missing.json()["error"]["message"]


def test_listing_only_shows_own_media(client: TestClient, registered: dict[str, str]) -> None:
    alice, bob, _ = _setup(client, registered)
    assert client.get("/api/v1/media", headers=auth_headers(bob)).json()["total"] == 0
    assert client.get("/api/v1/media", headers=auth_headers(alice)).json()["total"] == 1


def test_unauthenticated_access_is_rejected_everywhere(
    client: TestClient, registered: dict[str, str]
) -> None:
    _, _, mid = _setup(client, registered)
    client.cookies.clear()
    for method, path in [
        ("GET", "/api/v1/media"),
        ("GET", f"/api/v1/media/{mid}"),
        ("GET", f"/api/v1/media/{mid}/content"),
        ("DELETE", f"/api/v1/media/{mid}"),
    ]:
        r = client.request(method, path, headers={"X-Requested-With": "FoodVerseWeb"})
        assert r.status_code == 401, (method, path)


def test_malformed_ids_are_validation_errors(
    client: TestClient, registered: dict[str, str]
) -> None:
    h = auth_headers(registered["token"])
    for bad in ("not-a-uuid", "../../etc/passwd", "1"):
        assert client.get(f"/api/v1/media/{bad}", headers=h).status_code in (404, 422)
        assert client.get(f"/api/v1/media/{bad}/content", headers=h).status_code in (404, 422)


def test_deleting_an_account_row_removes_media_rows(
    client: TestClient, registered: dict[str, str]
) -> None:
    """Rows cascade with the user; documents that file cleanup is a separate (future) job."""
    from sqlalchemy import text

    from app.db.session import get_session_factory

    _setup(client, registered)
    with get_session_factory()() as db:
        db.execute(text("DELETE FROM users"))
        db.commit()
        assert db.execute(text("SELECT count(*) FROM media_assets")).scalar() == 0
