import json
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.ai.freshness import WITHHELD_TEXT
from app.ai.vision import (
    VisionBadOutputError,
    VisionModelMissingError,
    VisionRateLimitedError,
    VisionTimeoutError,
    VisionUnavailableError,
)
from app.core.config import get_settings
from app.db.session import get_session_factory
from app.models import MediaAsset, MediaKind
from tests.conftest import CSRF, auth_headers, register_user
from tests.food_helpers import FakeVision, install, upload_photo

Make = Callable[..., TestClient]
URL = "/api/v1/freshness/assessments"


def model_json(**over: Any) -> str:
    base: dict[str, Any] = {
        "image_quality": "clear",
        "food_visible": True,
        "matches_confirmed_food": "yes",
        "observations": [],
        "limitations": [],
        "notes": None,
    }
    base.update(over)
    return json.dumps(base)


MOLD = {
    "feature": "mold_like_growth",
    "description": "Fuzzy white patch",
    "location": "upper left",
    "severity": "moderate",
    "certainty": "clearly_visible",
}
BRUISE = {**MOLD, "feature": "bruising", "description": "Brown soft spot"}


def world(
    make_client: Make, raw: str | None = None, **kw: Any
) -> tuple[TestClient, str, str, FakeVision]:
    fake = FakeVision(raw=raw if raw is not None else model_json(), **kw)
    c = make_client()
    install(c, vision=fake, use_usda=False)
    return c, register_user(c, "alice@example.com"), register_user(c, "bob@example.com"), fake


def body(media_id: str | None, **over: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "media_id": media_id,
        "food_name": "Apple",
        "food_category": "fruit",
    }
    payload.update(over)
    return payload


def post(c: TestClient, tok: str, payload: dict[str, Any]) -> Any:
    return c.post(URL, headers=auth_headers(tok), json=payload)


# ---------------- capabilities ----------------
def test_capabilities_list_choices_and_state_vision_is_not_configured(make_client: Make) -> None:
    c = make_client()
    tok = register_user(c, "a@example.com")
    r = c.get("/api/v1/freshness/capabilities", headers=auth_headers(tok)).json()
    assert r["vision"]["configured"] is False and r["vision"]["message"]
    assert {x["value"] for x in r["categories"]} >= {"fruit", "meat_poultry", "cooked_food"}
    assert {x["value"] for x in r["storage_conditions"]} == {
        "refrigerator",
        "freezer",
        "room_temperature",
        "unknown",
    }
    assert r["classifier_enabled"] is False and "not a statement" in r["verdict_notice"]


def test_every_endpoint_requires_authentication(client: TestClient) -> None:
    some = uuid.uuid4()
    for method, path in (
        ("get", "/api/v1/freshness/capabilities"),
        ("post", URL),
        ("get", URL),
        ("get", f"{URL}/{some}"),
        ("delete", f"{URL}/{some}"),
    ):
        assert getattr(client, method)(path, headers=CSRF).status_code == 401, path


# ---------------- happy paths and honest labels ----------------
def test_clear_image_with_no_findings_is_not_called_safe(make_client: Make) -> None:
    c, alice, _, fake = world(make_client)
    r = post(c, alice, body(upload_photo(c, alice)))
    assert r.status_code == 201, r.text
    d = r.json()
    assert d["label"] == "no_obvious_visible_concern"
    assert d["label_text"] == "No obvious visible concern in this image"
    a = d["result"]
    assert a["advice"]["level"] == "general_caution"
    assert "cannot confirm safety" in a["advice"]["headline"].lower()
    assert any("invisible" in n for n in a["advice"]["general_notes"])
    assert "not a statement" in a["verdict_notice"]
    assert a["provider"] == {"name": "fake", "model": "fake-vision-1", "external": False}
    assert a["classifier_result"] is None
    flat = json.dumps(d).lower()
    assert "freshness_score" not in flat and "percent" not in flat and '"safe"' not in flat
    assert fake.calls == 1 and fake.images[0][:8] == b"\x89PNG\r\n\x1a\n"
    assert (
        "apple" in fake.prompts[0].lower()
        and "do not say whether the food is safe" in fake.prompts[0].lower()
    )


def test_visible_concern_keeps_observation_and_advice_separate(make_client: Make) -> None:
    c, alice, _, _ = world(
        make_client, model_json(observations=[BRUISE], limitations=["Back not visible"])
    )
    d = post(c, alice, body(upload_photo(c, alice))).json()
    assert d["label"] == "visible_concern_observed"
    assert d["result"]["findings"]["observations"][0] == {
        "feature": "bruising",
        "feature_label": "Bruising",
        "description": "Brown soft spot",
        "location": "upper left",
        "severity": "moderate",
        "certainty": "clearly_visible",
    }
    assert d["result"]["findings"]["limitations"] == ["Back not visible"]
    assert d["result"]["advice"]["level"] == "use_caution"
    assert d["result"]["advice"]["category_cautions"]


def test_mold_recommends_discarding(make_client: Make) -> None:
    c, alice, _, _ = world(make_client, model_json(observations=[MOLD]))
    d = post(c, alice, body(upload_photo(c, alice), food_category="bread_baked")).json()
    assert d["result"]["advice"]["level"] == "discard_recommended"
    assert any("Do not eat it" in s for s in d["result"]["advice"]["steps"])


@pytest.mark.parametrize(
    "reply",
    [
        model_json(image_quality="unusable"),
        model_json(food_visible=False),
        model_json(matches_confirmed_food="no"),
        model_json(image_quality="limited"),
        model_json(matches_confirmed_food="unsure"),
        model_json(image_quality="unusable", observations=[BRUISE]),
    ],
)
def test_unclear_or_inappropriate_images_are_inconclusive(make_client: Make, reply: str) -> None:
    c, alice, _, _ = world(make_client, reply)
    d = post(c, alice, body(upload_photo(c, alice))).json()
    assert d["label"] == "inconclusive" and d["label_text"] == "Inconclusive"
    a = d["result"]
    assert a["assessment"]["inconclusive_reasons"] and a["advice"]["retake_tips"]
    assert a["advice"]["level"] != "general_caution"


def test_model_verdicts_are_withheld_and_never_change_the_label(make_client: Make) -> None:
    risky = {**BRUISE, "description": "Looks perfectly safe to eat"}
    reply = model_json(
        observations=[risky], notes="Freshness score 90%", safe=True, verdict="fresh"
    )
    c, alice, _, _ = world(make_client, reply)
    d = post(c, alice, body(upload_photo(c, alice))).json()
    f = d["result"]["findings"]
    assert f["observations"][0]["description"] == WITHHELD_TEXT and f["notes"] == WITHHELD_TEXT
    assert f["withheld_text_count"] == 2
    assert d["label"] == "visible_concern_observed"
    assert "safe to eat" not in json.dumps(d)


def test_user_details_drive_guidance_independent_of_the_image(make_client: Make) -> None:
    c, alice, _, _ = world(make_client)  # image: nothing seen
    today = datetime.now(UTC).date()
    d = post(
        c,
        alice,
        body(
            upload_photo(c, alice),
            food_category="meat_poultry",
            storage_condition="room_temperature",
            storage_duration={"amount": 5, "unit": "hours"},
            packaging="opened",
            use_by_date=(today - timedelta(days=1)).isoformat(),
            purchased_on=(today - timedelta(days=3)).isoformat(),
            notes="  left on the counter  ",
        ),
    ).json()
    assert d["label"] == "no_obvious_visible_concern"  # the image said nothing...
    adv = d["result"]["advice"]
    assert adv["level"] == "discard_recommended"  # ...but the handling history says discard
    codes = {r["code"] for r in adv["reasons"]}
    assert {"left_out_too_long", "use_by_passed"} <= codes
    assert d["result"]["inputs"]["storage_hours"] == 5
    assert d["result"]["inputs"]["notes"] == "left on the counter"


def test_storage_duration_days_are_converted_to_hours(make_client: Make) -> None:
    c, alice, _, _ = world(make_client)
    d = post(
        c,
        alice,
        body(
            upload_photo(c, alice),
            food_category="cooked_food",
            storage_condition="refrigerator",
            storage_duration={"amount": 5, "unit": "days"},
        ),
    ).json()
    assert d["result"]["inputs"]["storage_hours"] == 120
    assert d["result"]["advice"]["level"] == "discard_recommended"


# ---------------- guidance-only mode (works with the AI offline) ----------------
def test_guidance_only_never_contacts_the_model(make_client: Make) -> None:
    c, alice, _, fake = world(make_client)
    r = post(c, alice, body(None, analyze_image=False, food_category="cooked_food"))
    assert r.status_code == 201, r.text
    d = r.json()
    assert d["label"] == "inconclusive" and d["image_analysed"] is False
    assert d["result"]["provider"] is None and d["result"]["findings"]["analysed"] is False
    assert [x["code"] for x in d["result"]["assessment"]["inconclusive_reasons"]] == [
        "image_not_analysed"
    ]
    assert d["result"]["advice"]["category_cautions"] and fake.calls == 0


def test_guidance_only_works_when_no_provider_is_configured(make_client: Make) -> None:
    c = make_client()  # real factory: AI disabled
    tok = register_user(c, "a@example.com")
    assert post(c, tok, body(None, analyze_image=False)).status_code == 201
    media = upload_photo(c, tok)
    r = post(c, tok, body(media))
    assert r.status_code == 503 and r.json()["error"]["code"] == "vision_unavailable"


def test_photo_can_be_attached_without_being_analysed(make_client: Make) -> None:
    c, alice, bob, fake = world(make_client)
    media = upload_photo(c, alice)
    d = post(c, alice, body(media, analyze_image=False)).json()
    assert d["media_id"] == media and d["image_analysed"] is False and fake.calls == 0
    bobs = post(c, bob, body(media, analyze_image=False))
    assert bobs.status_code == 404  # still ownership checked


# ---------------- provider errors: nothing is saved, nothing is faked ----------------
@pytest.mark.parametrize(
    ("error", "status"),
    [
        (VisionUnavailableError("down"), 503),
        (VisionModelMissingError("missing"), 503),
        (VisionTimeoutError("slow"), 504),
        (VisionBadOutputError("bad"), 502),
        (VisionRateLimitedError("busy"), 429),
    ],
)
def test_provider_errors_map_to_safe_errors_and_save_nothing(
    make_client: Make, error: Exception, status: int
) -> None:
    c, alice, _, _ = world(make_client, error=error)
    r = post(c, alice, body(upload_photo(c, alice)))
    assert r.status_code == status
    assert set(r.json()["error"]) >= {"code", "message", "request_id"}
    assert c.get(URL, headers=auth_headers(alice)).json()["total"] == 0
    assert c.get("/api/v1/history", headers=auth_headers(alice)).json()["total"] == 0


@pytest.mark.parametrize(
    "reply",
    [
        "",
        "not json",
        "[]",
        "{}",
        model_json(image_quality="excellent"),
        model_json(observations="x"),
    ],
)
def test_malformed_model_output_is_a_502_and_saves_nothing(make_client: Make, reply: str) -> None:
    c, alice, _, _ = world(make_client, reply)
    r = post(c, alice, body(upload_photo(c, alice)))
    assert r.status_code == 502 and r.json()["error"]["code"] == "vision_bad_output"
    assert c.get(URL, headers=auth_headers(alice)).json()["total"] == 0


def test_analysis_is_rate_limited_per_user(make_client: Make) -> None:
    fake = FakeVision(raw=model_json())
    c = make_client(scan_rate_limit_per_minute=2)
    install(c, vision=fake, use_usda=False)
    tok = register_user(c, "a@example.com")
    media = upload_photo(c, tok)
    codes = [post(c, tok, body(media)).status_code for _ in range(3)]
    assert codes == [201, 201, 429] and fake.calls == 2


# ---------------- invalid images ----------------
def test_unknown_foreign_and_non_image_media_are_rejected(make_client: Make) -> None:
    c, alice, bob, fake = world(make_client)
    media = upload_photo(c, alice)
    assert post(c, alice, body(str(uuid.uuid4()))).status_code == 404
    assert post(c, bob, body(media)).status_code == 404
    with get_session_factory()() as db:
        owner = db.get(MediaAsset, uuid.UUID(media)).owner_id  # type: ignore[union-attr]
        video = MediaAsset(
            owner_id=owner,
            kind=MediaKind.VIDEO,
            content_type="video/mp4",
            display_name="v.mp4",
            size_bytes=3,
            storage_key="x/v.mp4",
            sha256="0" * 64,
        )
        db.add(video)
        db.commit()
        vid = str(video.id)
    r = post(c, alice, body(vid))
    assert r.status_code == 422 and r.json()["error"]["code"] == "invalid_item"
    assert fake.calls == 0


def test_corrupt_stored_image_is_a_clean_422(make_client: Make) -> None:
    from app.media.storage import LocalStorage

    c, alice, _, fake = world(make_client)
    media = upload_photo(c, alice)
    with get_session_factory()() as db:
        key = db.get(MediaAsset, uuid.UUID(media)).storage_key  # type: ignore[union-attr]
    path: Path = LocalStorage(get_settings().media_root)._path(key)
    path.write_bytes(b"this is not an image")
    # the provider is real here so the image really is decoded before any request is made
    from app.ai.ollama_vision import OllamaVisionProvider

    real = OllamaVisionProvider("http://localhost:1", "m", 1)
    from app.api.deps import get_vision_factory

    c.app.dependency_overrides[get_vision_factory] = lambda: lambda: real  # type: ignore[attr-defined]
    r = post(c, alice, body(media))
    assert r.status_code == 422 and r.json()["error"]["code"] == "invalid_image"
    assert fake.calls == 0 and c.get(URL, headers=auth_headers(alice)).json()["total"] == 0


def test_invalid_uploads_never_reach_the_feature(make_client: Make) -> None:
    c, alice, _, _ = world(make_client)
    r = c.post(
        "/api/v1/media",
        headers=auth_headers(alice),
        files={"file": ("x.png", b"not an image", "image/png")},
    )
    assert (
        r.status_code in (415, 422) and c.get(URL, headers=auth_headers(alice)).json()["total"] == 0
    )


# ---------------- input validation ----------------
@pytest.mark.parametrize(
    "over",
    [
        {"food_name": "   "},
        {"food_name": "x" * 81},
        {"food_category": "spaceship"},
        {"storage_condition": "garage"},
        {"packaging": "wrapped"},
        {"storage_duration": {"amount": -1, "unit": "hours"}},
        {"storage_duration": {"amount": 400, "unit": "days"}},
        {"storage_duration": {"amount": 1, "unit": "weeks"}},
        {"use_by_date": "1980-01-01"},
        {"use_by_date": "not-a-date"},
        {"purchased_on": (datetime.now(UTC) + timedelta(days=5)).date().isoformat()},
        {"assessed_on": (datetime.now(UTC) + timedelta(days=9)).date().isoformat()},
        {"notes": "x" * 501},
        {"freshness_percent": 80},
        {"media_id": "nope"},
    ],
)
def test_invalid_input_is_rejected_before_anything_runs(
    make_client: Make, over: dict[str, Any]
) -> None:
    c, alice, _, fake = world(make_client)
    payload = {**body(upload_photo(c, alice)), **over}
    assert post(c, alice, payload).status_code == 422
    assert fake.calls == 0


def test_analysis_without_a_photo_is_rejected(make_client: Make) -> None:
    c, alice, _, _ = world(make_client)
    assert post(c, alice, body(None)).status_code == 422


def test_writes_require_the_csrf_header(make_client: Make) -> None:
    c, alice, _, _ = world(make_client)
    h = {"Authorization": f"Bearer {alice}"}
    assert c.post(URL, headers=h, json=body(None, analyze_image=False)).status_code == 403
    made = post(c, alice, body(None, analyze_image=False)).json()
    assert c.delete(f"{URL}/{made['id']}", headers=h).status_code == 403


# ---------------- persistence, history, detail, delete ----------------
def test_assessments_persist_with_full_audit(make_client: Make) -> None:
    c, alice, _, _ = world(make_client, model_json(observations=[BRUISE]))
    made = post(c, alice, body(upload_photo(c, alice), storage_condition="refrigerator")).json()
    got = c.get(f"{URL}/{made['id']}", headers=auth_headers(alice)).json()
    assert got == made
    assert got["created_at"] and got["result"]["generated_at"]
    assert got["result"]["inputs"]["storage_condition"] == "refrigerator"
    assert got["result"]["provider"]["model"] == "fake-vision-1"
    assert got["result"]["food"] == {
        "name": "Apple",
        "category": "fruit",
        "category_label": "Fruit",
    }


def test_history_list_filters_pages_and_orders_newest_first(make_client: Make) -> None:
    c, alice, _, _ = world(make_client)
    h = auth_headers(alice)
    for name, cat in [("A", "fruit"), ("B", "fruit"), ("C", "meat_poultry")]:
        assert (
            post(
                c, alice, body(None, analyze_image=False, food_name=name, food_category=cat)
            ).status_code
            == 201
        )
    page = c.get(f"{URL}?page_size=2", headers=h).json()
    assert (page["total"], page["pages"]) == (3, 2) and page["items"][0]["food_name"] == "C"
    assert c.get(f"{URL}?category=fruit", headers=h).json()["total"] == 2
    assert c.get(f"{URL}?label=inconclusive", headers=h).json()["total"] == 3
    assert c.get(f"{URL}?label=no_obvious_visible_concern", headers=h).json()["total"] == 0
    for q in ("label=safe", "category=x", "page=0", "page_size=101"):
        assert c.get(f"{URL}?{q}", headers=h).status_code == 422


def test_saved_checks_appear_in_shared_history_and_module_is_available(make_client: Make) -> None:
    c, alice, _, _ = world(make_client)
    made = post(c, alice, body(None, analyze_image=False)).json()
    hist = c.get("/api/v1/history?module=freshness", headers=auth_headers(alice)).json()
    assert hist["total"] == 1 and hist["items"][0]["id"] == made["id"]
    assert hist["items"][0]["summary"] == "Inconclusive"
    mods = {
        m["key"]: m["available"]
        for m in c.get("/api/v1/modules", headers=auth_headers(alice)).json()
    }
    assert mods["freshness"] is True


def test_delete_removes_the_check_everywhere(make_client: Make) -> None:
    c, alice, _, _ = world(make_client)
    h = auth_headers(alice)
    made = post(c, alice, body(None, analyze_image=False)).json()
    assert c.delete(f"{URL}/{made['id']}", headers=h).status_code == 204
    assert c.get(f"{URL}/{made['id']}", headers=h).status_code == 404
    assert c.get(URL, headers=h).json()["total"] == 0
    assert c.get("/api/v1/history", headers=h).json()["total"] == 0
    assert c.delete(f"{URL}/{made['id']}", headers=h).status_code == 404


def test_deleting_the_photo_keeps_the_check(make_client: Make) -> None:
    c, alice, _, _ = world(make_client)
    h = auth_headers(alice)
    media = upload_photo(c, alice)
    made = post(c, alice, body(media)).json()
    assert c.delete(f"/api/v1/media/{media}", headers=h).status_code == 204
    kept = c.get(f"{URL}/{made['id']}", headers=h).json()
    assert kept["media_id"] is None and kept["result"]["findings"]["analysed"] is True


# ---------------- access control ----------------
def test_users_cannot_see_or_delete_each_others_checks(make_client: Make) -> None:
    c, alice, bob, _ = world(make_client)
    made = post(c, alice, body(None, analyze_image=False)).json()
    hb = auth_headers(bob)
    assert c.get(f"{URL}/{made['id']}", headers=hb).status_code == 404
    assert c.delete(f"{URL}/{made['id']}", headers=hb).status_code == 404
    assert c.get(URL, headers=hb).json()["total"] == 0
    assert c.get("/api/v1/history", headers=hb).json()["total"] == 0
    assert c.delete(f"/api/v1/history/{made['id']}", headers=hb).status_code == 404
    assert c.get(f"{URL}/{made['id']}", headers=auth_headers(alice)).status_code == 200
    assert c.get(f"{URL}/{uuid.uuid4()}", headers=hb).status_code == 404
