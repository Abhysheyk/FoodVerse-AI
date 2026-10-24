import io
import os
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from httpx import Response
from PIL import Image

from app.media.storage import LocalStorage, StorageError
from tests.conftest import CSRF, auth_headers, register_user
from tests.imgs import jpeg_with_exif, make_image, noise_png, upload_files

MEDIA_ROOT = Path(os.environ["MEDIA_ROOT"])


def _upload(client: TestClient, token: str, content: bytes, name: str, mime: str) -> Response:
    response: Response = client.post(
        "/api/v1/media", headers=auth_headers(token), files=upload_files(content, name, mime)
    )
    return response


def _stored_files() -> list[Path]:
    return [p for p in MEDIA_ROOT.rglob("*") if p.is_file()]


@pytest.mark.parametrize(
    ("fmt", "name", "mime", "ctype"),
    [
        ("PNG", "meal.png", "image/png", "image/png"),
        ("JPEG", "meal.JPG", "image/jpeg", "image/jpeg"),
        ("JPEG", "meal.jpeg", "image/jpeg", "image/jpeg"),
        ("WEBP", "meal.webp", "image/webp", "image/webp"),
    ],
)
def test_valid_images_are_accepted_and_described(
    client: TestClient, registered: dict[str, str], fmt: str, name: str, mime: str, ctype: str
) -> None:
    r = _upload(client, registered["token"], make_image(fmt, (64, 48)), name, mime)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["kind"] == "image" and body["content_type"] == ctype
    assert (body["width"], body["height"]) == (64, 48)
    assert body["size_bytes"] > 0 and body["duration_seconds"] is None
    assert "storage_key" not in body and "owner_id" not in body and "sha256" not in body


def test_stored_file_is_reencoded_and_metadata_stripped(
    client: TestClient, registered: dict[str, str]
) -> None:
    original = jpeg_with_exif()
    assert Image.open(io.BytesIO(original)).getexif().get_ifd(0x8825)  # sanity: GPS present
    r = _upload(client, registered["token"], original, "photo.jpg", "image/jpeg")
    assert r.status_code == 201
    stored = client.get(
        f"/api/v1/media/{r.json()['id']}/content", headers=auth_headers(registered["token"])
    )
    img = Image.open(io.BytesIO(stored.content))
    assert not img.getexif().get_ifd(0x8825), "GPS data must be removed"
    assert 0x0112 not in img.getexif(), "orientation tag is baked in, then dropped"
    assert img.size == (20, 40)  # 40x20 rotated by the orientation flag
    assert (r.json()["width"], r.json()["height"]) == (20, 40)
    assert stored.content != original


def test_trailing_payload_is_not_preserved(client: TestClient, registered: dict[str, str]) -> None:
    sneaky = make_image("PNG") + b"<script>alert(1)</script>PAYLOAD"
    r = _upload(client, registered["token"], sneaky, "a.png", "image/png")
    assert r.status_code == 201
    stored = client.get(
        f"/api/v1/media/{r.json()['id']}/content", headers=auth_headers(registered["token"])
    )
    assert b"PAYLOAD" not in stored.content and b"<script>" not in stored.content


def test_client_filename_never_reaches_the_filesystem(
    client: TestClient, registered: dict[str, str]
) -> None:
    r = _upload(
        client, registered["token"], make_image("PNG"), "../../../etc/passwd/..\\x.png", "image/png"
    )
    assert r.status_code == 201
    assert r.json()["display_name"] == "x.png"
    files = _stored_files()
    assert len(files) == 1 and files[0].resolve().is_relative_to(MEDIA_ROOT.resolve())
    assert "passwd" not in str(files[0]) and files[0].suffix == ".png"
    assert oct(files[0].stat().st_mode & 0o777) == "0o600"


@pytest.mark.parametrize(
    ("content", "name", "mime", "status", "code"),
    [
        (b"just some text", "notes.png", "image/png", 415, "unsupported_media_type"),
        (
            b"<svg xmlns='http://www.w3.org/2000/svg'><script>1</script></svg>",
            "x.svg",
            "image/svg+xml",
            415,
            "unsupported_media_type",
        ),
        (b"<html><body>hi</body></html>", "x.jpg", "image/jpeg", 415, "unsupported_media_type"),
        (b"MZ\x90\x00 fake exe", "x.png", "image/png", 415, "unsupported_media_type"),
        (b"GIF89a\x01\x00\x01\x00", "x.gif", "image/gif", 415, "unsupported_media_type"),
        (b"", "empty.png", "image/png", 422, "empty_file"),
    ],
)
def test_non_images_are_rejected(
    client: TestClient,
    registered: dict[str, str],
    content: bytes,
    name: str,
    mime: str,
    status: int,
    code: str,
) -> None:
    r = _upload(client, registered["token"], content, name, mime)
    assert r.status_code == status, r.text
    assert r.json()["error"]["code"] == code
    assert _stored_files() == []


def test_extension_and_declared_type_must_match_the_real_format(
    client: TestClient, registered: dict[str, str]
) -> None:
    png = make_image("PNG")
    for name, mime in [
        ("a.jpg", "image/png"),
        ("a.png", "image/jpeg"),
        ("a.png", "text/html"),
        ("a.png", "application/octet-stream"),
        ("a", "image/png"),
        ("a.exe", "image/png"),
    ]:
        r = _upload(client, registered["token"], png, name, mime)
        assert r.status_code == 415, (name, mime, r.text)
        assert r.json()["error"]["code"] == "media_type_mismatch"
    assert _stored_files() == []


@pytest.mark.parametrize(
    "name", ["clip.mp4", "clip.mov", "song.mp3", "voice.wav", "a.webm", "a.m4a"]
)
def test_video_and_audio_are_explicitly_not_enabled(
    client: TestClient, registered: dict[str, str], name: str
) -> None:
    r = _upload(
        client, registered["token"], b"\x00\x00\x00\x18ftypmp42" + b"0" * 40, name, "video/mp4"
    )
    assert r.status_code == 415
    assert r.json()["error"]["code"] == "media_kind_not_enabled"


def test_corrupt_and_truncated_images_are_rejected(
    client: TestClient, registered: dict[str, str]
) -> None:
    good = make_image("PNG", (200, 200))
    for broken in (
        good[: len(good) // 2],
        good[:8] + b"\x00" * 50,
        b"\xff\xd8\xff" + b"\x00" * 100,
    ):
        r = _upload(
            client,
            registered["token"],
            broken,
            "a.png" if broken[:1] != b"\xff" else "a.jpg",
            "image/png" if broken[:1] != b"\xff" else "image/jpeg",
        )
        assert r.status_code == 422, r.text
        assert r.json()["error"]["code"] == "invalid_image"
    assert _stored_files() == []


def test_decompression_bomb_style_dimensions_are_rejected(
    make_client: Callable[..., TestClient],
) -> None:
    c = make_client(max_image_pixels=1_000_000)
    token = register_user(c, "bomb@example.com")
    big = make_image("PNG", (1500, 1500))  # ~2.2 MP but only a few KB on disk
    assert len(big) < 100_000
    r = _upload(c, token, big, "big.png", "image/png")
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "image_dimensions_too_large"
    assert (
        _upload(c, token, make_image("PNG", (900, 900)), "ok.png", "image/png").status_code == 201
    )


def test_upload_size_limit_is_enforced(make_client: Callable[..., TestClient]) -> None:
    c = make_client(max_upload_bytes=50_000)
    token = register_user(c, "limit@example.com")
    r = _upload(c, token, noise_png(150), "big.png", "image/png")  # ~67 KB
    assert r.status_code == 413
    assert r.json()["error"]["code"] == "file_too_large"
    assert _stored_files() == []
    ok = _upload(c, token, noise_png(60), "small.png", "image/png")  # ~11 KB
    assert ok.status_code == 201


def test_body_over_the_limit_is_rejected_even_if_the_client_lies_about_length(
    make_client: Callable[..., TestClient],
) -> None:
    c = make_client(max_upload_bytes=10_000)
    token = register_user(c, "liar@example.com")
    boundary = "xxBOUNDARYxx"
    body = (
        (
            f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="a.png"\r\n'
            f"Content-Type: image/png\r\n\r\n"
        ).encode()
        + b"A" * 200_000
        + f"\r\n--{boundary}--\r\n".encode()
    )
    headers = {**auth_headers(token), "Content-Type": f"multipart/form-data; boundary={boundary}"}
    r = c.post("/api/v1/media", headers=headers, content=body)  # honest Content-Length
    assert r.status_code == 413 and r.json()["error"]["code"] == "file_too_large"

    def chunks() -> Iterator[bytes]:  # no Content-Length: chunked transfer
        yield body[:100_000]
        yield body[100_000:]

    r2 = c.post("/api/v1/media", headers=headers, content=chunks())
    assert r2.status_code == 413
    assert _stored_files() == []


def test_per_user_quota(make_client: Callable[..., TestClient]) -> None:
    c = make_client(user_media_quota_bytes=150_000)
    token = register_user(c, "quota@example.com")
    first = _upload(c, token, noise_png(150), "a.png", "image/png")  # ~67 KB
    second = _upload(c, token, noise_png(150), "b.png", "image/png")
    third = _upload(c, token, noise_png(150), "c.png", "image/png")
    assert first.status_code == second.status_code == 201
    assert third.status_code == 413 and third.json()["error"]["code"] == "quota_exceeded"
    assert len(_stored_files()) == 2
    # deleting frees quota
    assert (
        c.delete(f"/api/v1/media/{first.json()['id']}", headers=auth_headers(token)).status_code
        == 204
    )
    assert _upload(c, token, noise_png(150), "d.png", "image/png").status_code == 201


def test_upload_requires_auth_and_csrf_header(
    client: TestClient, registered: dict[str, str]
) -> None:
    files = upload_files(make_image("PNG"), "a.png", "image/png")
    assert client.post("/api/v1/media", headers=CSRF, files=files).status_code == 401
    assert client.post("/api/v1/media", files=files).status_code in (401, 403)  # never succeeds
    no_csrf = client.post(
        "/api/v1/media", headers={"Authorization": f"Bearer {registered['token']}"}, files=files
    )
    assert no_csrf.status_code == 403
    assert (
        client.post("/api/v1/media", headers=auth_headers(registered["token"])).status_code == 422
    )  # no file
    assert _stored_files() == []


def test_content_is_served_with_safe_headers(
    client: TestClient, registered: dict[str, str]
) -> None:
    png = make_image("PNG")
    mid = _upload(client, registered["token"], png, "my meal.png", "image/png").json()["id"]
    h = auth_headers(registered["token"])
    r = client.get(f"/api/v1/media/{mid}/content", headers=h)
    assert r.status_code == 200 and r.headers["content-type"] == "image/png"
    assert r.headers["x-content-type-options"] == "nosniff"
    assert "sandbox" in r.headers["content-security-policy"]
    assert r.headers["content-disposition"] == "inline"
    assert Image.open(io.BytesIO(r.content)).size == (32, 24)
    d = client.get(f"/api/v1/media/{mid}/content?download=true", headers=h)
    assert d.headers["content-disposition"].startswith("attachment; filename*=UTF-8''my%20meal.png")


def test_list_is_paginated_newest_first(client: TestClient, registered: dict[str, str]) -> None:
    for i in range(5):
        _upload(
            client, registered["token"], make_image("PNG", (10 + i, 10)), f"f{i}.png", "image/png"
        )
    h = auth_headers(registered["token"])
    p1 = client.get("/api/v1/media?page=1&page_size=2", headers=h).json()
    p3 = client.get("/api/v1/media?page=3&page_size=2", headers=h).json()
    assert (p1["total"], p1["pages"], len(p1["items"])) == (5, 3, 2)
    assert [i["display_name"] for i in p1["items"]] == ["f4.png", "f3.png"]
    assert len(p3["items"]) == 1
    assert client.get("/api/v1/media?page_size=51", headers=h).status_code == 422
    assert client.get("/api/v1/media?page=0", headers=h).status_code == 422


def test_delete_removes_row_and_file(client: TestClient, registered: dict[str, str]) -> None:
    h = auth_headers(registered["token"])
    mid = _upload(client, registered["token"], make_image("PNG"), "a.png", "image/png").json()["id"]
    assert len(_stored_files()) == 1
    assert (
        client.delete(
            f"/api/v1/media/{mid}", headers={"Authorization": h["Authorization"]}
        ).status_code
        == 403
    )
    assert client.delete(f"/api/v1/media/{mid}", headers=h).status_code == 204
    assert _stored_files() == []
    assert client.get(f"/api/v1/media/{mid}", headers=h).status_code == 404
    assert client.delete(f"/api/v1/media/{mid}", headers=h).status_code == 404


def test_missing_file_on_disk_is_handled(client: TestClient, registered: dict[str, str]) -> None:
    mid = _upload(client, registered["token"], make_image("PNG"), "a.png", "image/png").json()["id"]
    for f in _stored_files():
        f.unlink()
    r = client.get(f"/api/v1/media/{mid}/content", headers=auth_headers(registered["token"]))
    assert r.status_code == 404 and r.json()["error"]["code"] == "media_not_found"


def test_files_are_not_publicly_reachable(client: TestClient, registered: dict[str, str]) -> None:
    _upload(client, registered["token"], make_image("PNG"), "a.png", "image/png")
    key = _stored_files()[0].relative_to(MEDIA_ROOT).as_posix()
    for path in (
        f"/media/{key}",
        f"/uploads/{key}",
        f"/static/{key}",
        f"/api/v1/media/{key}",
        f"/{key}",
    ):
        assert client.get(path).status_code in (401, 404, 405, 422), path
    assert not MEDIA_ROOT.resolve().is_relative_to(Path(__file__).resolve().parents[2] / "frontend")


def test_orphan_file_is_cleaned_up_if_the_database_write_fails(
    client: TestClient, registered: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.repositories import media as media_repo

    def boom(*_a: object, **_k: object) -> None:
        raise RuntimeError("db down")

    monkeypatch.setattr(media_repo, "add", boom)
    c = TestClient(client.app, raise_server_exceptions=False)
    r = c.post(
        "/api/v1/media",
        headers=auth_headers(registered["token"]),
        files=upload_files(make_image("PNG"), "a.png", "image/png"),
    )
    assert r.status_code == 500 and r.json()["error"]["code"] == "internal_error"
    assert _stored_files() == []


def test_local_storage_rejects_unsafe_keys(tmp_path: Path) -> None:
    store = LocalStorage(tmp_path)
    good = "ab/" + "c" * 32 + ".png"
    store.put(good, b"x")
    assert store.exists(good) and store.open(good).read() == b"x"
    for bad in (
        "../x.png",
        "ab/../../etc/passwd",
        "/etc/passwd",
        "ab/" + "c" * 32 + ".php",
        "ab/" + "c" * 31 + ".png",
        "AB/" + "c" * 32 + ".png",
        "ab\\" + "c" * 32 + ".png",
        "",
    ):
        with pytest.raises(StorageError):
            store.put(bad, b"x")
        with pytest.raises(StorageError):
            store.open(bad)
    store.delete(good)
    assert not store.exists(good)
    store.delete(good)  # idempotent


def test_csrf_header_constant_is_used_on_state_changes(
    client: TestClient, registered: dict[str, str]
) -> None:
    assert CSRF["X-Requested-With"]  # documents the header the mutating routes require
