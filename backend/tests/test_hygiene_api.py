import json
import uuid
from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.ai.hygiene import WITHHELD_TEXT
from app.ai.vision import (
    VisionBadOutputError, VisionRateLimitedError, VisionTimeoutError, VisionUnavailableError,
)
from app.domain import hygiene as rules
from tests.conftest import CSRF, auth_headers, register_user
from tests.food_helpers import FakeVision, install, upload_photo

Make = Callable[..., TestClient]
URL = "/api/v1/hygiene/inspections"


def model_json(**over: Any) -> str:
    base: dict[str, Any] = {
        "findings": [
            {
                "category": "surface_cleanliness",
                "description": "Greasy film on the cutting board",
                "location": "left side",
                "severity": "medium",
                "certainty": "clearly_visible",
            }
        ],
        "limitations": ["Cannot see inside the fridge"],
        "notes": None,
    }
    base.update(over)
    return json.dumps(base)


def world(make_client: Make, raw: str | None = None, **kw: Any) -> tuple[TestClient, str, str, FakeVision]:
    fake = FakeVision(raw=raw if raw is not None else model_json(), **kw)
    c = make_client()
    install(c, vision=fake, use_usda=False)
    return c, register_user(c, "alice@example.com"), register_user(c, "bob@example.com"), fake


def body(media_ids: list[str], **over: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "location_name": "Main kitchen",
        "location_type": "restaurant_kitchen",
        "area": "Prep station",
        "media_ids": media_ids,
        "notes": None,
    }
    payload.update(over)
    return payload


def post(c: TestClient, tok: str, payload: dict[str, Any]) -> Any:
    return c.post(URL, headers=auth_headers(tok), json=payload)


# ---------------- capabilities + auth ----------------
def test_capabilities_lists_choices_and_vision_state(make_client: Make) -> None:
    c = make_client()
    tok = register_user(c, "a@example.com")
    r = c.get("/api/v1/hygiene/capabilities", headers=auth_headers(tok)).json()
    assert r["vision"]["configured"] is False and r["vision"]["message"]
    assert {x["value"] for x in r["location_types"]} >= {"restaurant_kitchen", "home_kitchen"}
    assert {x["value"] for x in r["statuses"]} == {"draft", "in_review", "approved", "rejected"}
    assert any(item["item_id"] == "handwashing" for item in r["default_checklist"])
    assert r["max_photos"] == 8


def test_every_endpoint_requires_authentication(client: TestClient) -> None:
    some = uuid.uuid4()
    for method, path in (
        ("get", "/api/v1/hygiene/capabilities"),
        ("post", URL),
        ("get", URL),
        ("get", f"{URL}/{some}"),
        ("put", f"{URL}/{some}"),
        ("post", f"{URL}/{some}/analyze"),
        ("post", f"{URL}/{some}/submit"),
        ("post", f"{URL}/{some}/approve"),
        ("post", f"{URL}/{some}/reject"),
        ("delete", f"{URL}/{some}"),
        ("get", f"{URL}/{some}/report"),
    ):
        assert getattr(client, method)(path, headers=CSRF).status_code == 401, path


# ---------------- create / read / update / delete ----------------
def test_create_lists_and_reads_a_draft(make_client: Make) -> None:
    c, alice, _, _ = world(make_client)
    photo = upload_photo(c, alice)
    r = post(c, alice, body([photo], notes="routine check"))
    assert r.status_code == 201, r.text
    d = r.json()
    assert d["status"] == "draft" and d["status_label"] == "Draft"
    assert d["location_name"] == "Main kitchen" and d["area"] == "Prep station"
    assert d["photo_count"] == 1 and d["finding_count"] == 0
    assert d["media_ids"] == [photo]
    assert d["result"]["checklist"] and any(x["item_id"] == "handwashing" for x in d["result"]["checklist"])
    assert len(d["result"]["disclosures"]) >= 3
    assert any("pathogen" in x.lower() for x in d["result"]["disclosures"])
    assert len(d["result"]["not_assessable"]) >= 3

    listed = c.get(URL, headers=auth_headers(alice)).json()
    assert listed["total"] == 1 and listed["items"][0]["id"] == d["id"]

    got = c.get(f"{URL}/{d['id']}", headers=auth_headers(alice)).json()
    assert got == d


def test_delete_removes_from_list_and_history(make_client: Make) -> None:
    c, alice, _, _ = world(make_client)
    photo = upload_photo(c, alice)
    made = post(c, alice, body([photo])).json()
    h = auth_headers(alice)
    hist_before = c.get("/api/v1/history?module=hygiene", headers=h).json()
    assert hist_before["total"] == 1
    assert c.delete(f"{URL}/{made['id']}", headers=h).status_code == 204
    assert c.get(f"{URL}/{made['id']}", headers=h).status_code == 404
    assert c.get(URL, headers=h).json()["total"] == 0
    assert c.get("/api/v1/history?module=hygiene", headers=h).json()["total"] == 0


def test_ownership_isolation(make_client: Make) -> None:
    c, alice, bob, _ = world(make_client)
    photo = upload_photo(c, alice)
    made = post(c, alice, body([photo])).json()
    hb = auth_headers(bob)
    iid = made["id"]
    assert c.get(f"{URL}/{iid}", headers=hb).status_code == 404
    assert c.put(f"{URL}/{iid}", headers=hb, json={"expected_revision": 1, "notes": "x"}).status_code == 404
    assert c.delete(f"{URL}/{iid}", headers=hb).status_code == 404
    assert c.get(URL, headers=hb).json()["total"] == 0
    assert c.get(f"{URL}/{iid}", headers=auth_headers(alice)).status_code == 200


def test_cannot_attach_foreign_photo(make_client: Make) -> None:
    c, alice, bob, _ = world(make_client)
    photo = upload_photo(c, alice)
    r = post(c, bob, body([photo]))
    assert r.status_code == 404


def test_update_draft_edits_location_notes_and_findings(make_client: Make) -> None:
    c, alice, _, _ = world(make_client)
    photo = upload_photo(c, alice)
    made = post(c, alice, body([photo])).json()
    h = auth_headers(alice)
    upd = c.put(f"{URL}/{made['id']}", headers=h, json={
        "expected_revision": 1,
        "location_name": "Back kitchen",
        "area": "Dish station",
        "notes": "evening shift",
        "findings": [{
            "source": "user", "category": "tool_cleanliness", "severity": "high",
            "description": "Knife left on dirty board", "location": "middle",
            "certainty": "clearly_visible",
            "evidence_media_id": photo, "user_note": "Board is unwashed",
        }],
    })
    assert upd.status_code == 200, upd.text
    d = upd.json()
    assert d["location_name"] == "Back kitchen" and d["area"] == "Dish station"
    assert d["revision"] == 2 and d["finding_count"] == 1 and d["highest_severity"] == "high"
    f = d["result"]["findings"][0]
    assert f["source"] == "user" and f["category_label"] == "Tool cleanliness"
    assert f["suggested_action"]  # derived from fixed rules, not the client
    # Stale revision is rejected
    stale = c.put(f"{URL}/{made['id']}", headers=h, json={"expected_revision": 1, "notes": "x"})
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "inspection_revision_conflict"


# ---------------- analysis ----------------
def test_analyze_produces_labelled_model_findings_only(make_client: Make) -> None:
    c, alice, _, fake = world(make_client)
    photo = upload_photo(c, alice)
    made = post(c, alice, body([photo])).json()
    r = c.post(f"{URL}/{made['id']}/analyze", headers=auth_headers(alice))
    assert r.status_code == 200, r.text
    d = r.json()
    findings = d["result"]["findings"]
    assert len(findings) == 1
    f = findings[0]
    assert f["source"] == "model" and f["evidence_media_id"] == photo
    assert f["category_label"] == "Surface cleanliness"
    assert f["suggested_action"]
    assert d["result"]["provider"]["model"] == "fake-vision-1"
    assert d["result"]["model_limitations"] == ["Cannot see inside the fridge"]
    # No compliance/safety claims anywhere in the payload.
    flat = json.dumps(d).lower()
    for forbidden in ("compliant", "violation", "score:", "grade"):
        assert forbidden not in flat
    assert fake.calls == 1 and fake.images[0][:8] == b"\x89PNG\r\n\x1a\n"


def test_user_findings_survive_reanalysis(make_client: Make) -> None:
    c, alice, _, _ = world(make_client)
    photo = upload_photo(c, alice)
    made = post(c, alice, body([photo])).json()
    h = auth_headers(alice)
    c.put(f"{URL}/{made['id']}", headers=h, json={"findings": [{
        "source": "user", "category": "uncovered_food", "severity": "medium",
        "description": "Open rice pot", "location": "back",
        "certainty": "clearly_visible",
    }]})
    r = c.post(f"{URL}/{made['id']}/analyze", headers=h).json()
    sources = [f["source"] for f in r["result"]["findings"]]
    assert "user" in sources and "model" in sources


def test_verdict_language_in_model_text_is_withheld(make_client: Make) -> None:
    reply = model_json(findings=[{
        "category": "surface_cleanliness",
        "description": "Surface is compliant and safe to eat from",
        "location": "left", "severity": "low", "certainty": "clearly_visible",
    }], notes="Hygiene score 95%")
    c, alice, _, _ = world(make_client, reply)
    photo = upload_photo(c, alice)
    made = post(c, alice, body([photo])).json()
    r = c.post(f"{URL}/{made['id']}/analyze", headers=auth_headers(alice)).json()
    assert r["result"]["findings"][0]["description"] == WITHHELD_TEXT
    assert r["result"]["withheld_text_count"] >= 2
    assert "95%" not in json.dumps(r) and "compliant" not in json.dumps(r).lower()


@pytest.mark.parametrize("reply", [
    "", "not json", "[]", "{}", '{"findings": "x"}',
    json.dumps({"findings": [{"category": "bogus", "description": "x", "severity": "low", "certainty": "clearly_visible"}]}),
    json.dumps({"findings": [{"category": "surface_cleanliness", "description": "x", "severity": "critical", "certainty": "clearly_visible"}]}),
    json.dumps({"findings": [{"category": "surface_cleanliness", "description": "", "severity": "low", "certainty": "clearly_visible"}]}),
])
def test_bad_model_output_is_502_and_saves_nothing(make_client: Make, reply: str) -> None:
    c, alice, _, _ = world(make_client, reply)
    photo = upload_photo(c, alice)
    made = post(c, alice, body([photo])).json()
    r = c.post(f"{URL}/{made['id']}/analyze", headers=auth_headers(alice))
    assert r.status_code == 502 and r.json()["error"]["code"] == "vision_bad_output"
    # Nothing persisted; status still draft, findings still empty.
    after = c.get(f"{URL}/{made['id']}", headers=auth_headers(alice)).json()
    assert after["result"]["findings"] == []


@pytest.mark.parametrize("err,status", [
    (VisionUnavailableError("down"), 503),
    (VisionTimeoutError("slow"), 504),
    (VisionRateLimitedError("busy"), 429),
])
def test_provider_errors_map_to_safe_errors(make_client: Make, err: Exception, status: int) -> None:
    c, alice, _, _ = world(make_client, error=err)
    photo = upload_photo(c, alice)
    made = post(c, alice, body([photo])).json()
    r = c.post(f"{URL}/{made['id']}/analyze", headers=auth_headers(alice))
    assert r.status_code == status
    assert set(r.json()["error"]) >= {"code", "message", "request_id"}


def test_analyze_requires_photos(make_client: Make) -> None:
    c, alice, _, _ = world(make_client)
    made = post(c, alice, body([])).json()
    r = c.post(f"{URL}/{made['id']}/analyze", headers=auth_headers(alice))
    assert r.status_code == 422 and r.json()["error"]["code"] == "no_photos"


# ---------------- review workflow ----------------
def test_full_lifecycle_draft_to_approved(make_client: Make) -> None:
    c, alice, _, _ = world(make_client)
    photo = upload_photo(c, alice)
    made = post(c, alice, body([photo])).json()
    h = auth_headers(alice)
    # cannot submit without photos -> we have one, but let's verify submit works
    s = c.post(f"{URL}/{made['id']}/submit", headers=h)
    assert s.status_code == 200 and s.json()["status"] == "in_review"
    # cannot edit findings while in review
    edit = c.put(f"{URL}/{made['id']}", headers=h, json={"findings": []})
    assert edit.status_code == 409 and edit.json()["error"]["code"] == "inspection_in_review"
    a = c.post(f"{URL}/{made['id']}/approve", headers=h, json={"review_notes": None})
    assert a.status_code == 200 and a.json()["status"] == "approved"
    assert a.json()["reviewed_at"]
    # approved is read-only
    locked = c.put(f"{URL}/{made['id']}", headers=h, json={"notes": "x"})
    assert locked.status_code == 409 and locked.json()["error"]["code"] == "inspection_locked"


def test_reject_requires_notes_and_allows_rework(make_client: Make) -> None:
    c, alice, _, _ = world(make_client)
    photo = upload_photo(c, alice)
    made = post(c, alice, body([photo])).json()
    h = auth_headers(alice)
    c.post(f"{URL}/{made['id']}/submit", headers=h)
    no_notes = c.post(f"{URL}/{made['id']}/reject", headers=h, json={"review_notes": None})
    assert no_notes.status_code == 422 and no_notes.json()["error"]["code"] == "review_notes_required"
    rej = c.post(f"{URL}/{made['id']}/reject", headers=h, json={"review_notes": "Add kitchen-area photo"})
    assert rej.status_code == 200 and rej.json()["status"] == "rejected"
    assert rej.json()["review_notes"] == "Add kitchen-area photo"
    # rejected is editable again
    edit = c.put(f"{URL}/{made['id']}", headers=h, json={"findings": [{
        "source": "user", "category": "waste_management", "severity": "high",
        "description": "Open bin next to prep", "location": "back",
        "certainty": "clearly_visible",
    }]})
    assert edit.status_code == 200 and edit.json()["finding_count"] == 1


def test_approved_cannot_be_rejected(make_client: Make) -> None:
    c, alice, _, _ = world(make_client)
    photo = upload_photo(c, alice)
    made = post(c, alice, body([photo])).json()
    h = auth_headers(alice)
    c.post(f"{URL}/{made['id']}/submit", headers=h)
    c.post(f"{URL}/{made['id']}/approve", headers=h, json={"review_notes": None})
    r = c.post(f"{URL}/{made['id']}/reject", headers=h, json={"review_notes": "late"})
    assert r.status_code == 409


# ---------------- filters, pagination, report ----------------
def test_list_filters_and_pagination(make_client: Make) -> None:
    c, alice, _, _ = world(make_client)
    h = auth_headers(alice)
    photo = upload_photo(c, alice)
    a = post(c, alice, body([photo], location_name="A")).json()
    b = post(c, alice, body([photo], location_name="B", location_type="home_kitchen")).json()
    c.post(f"{URL}/{a['id']}/submit", headers=h)
    page = c.get(f"{URL}?page_size=1", headers=h).json()
    assert page["total"] == 2 and page["pages"] == 2
    only_home = c.get(f"{URL}?location_type=home_kitchen", headers=h).json()
    assert only_home["total"] == 1 and only_home["items"][0]["id"] == b["id"]
    draft = c.get(f"{URL}?status=draft", headers=h).json()
    assert draft["total"] == 1 and draft["items"][0]["id"] == b["id"]


def test_report_html_is_self_contained_and_has_disclosures(make_client: Make) -> None:
    c, alice, _, _ = world(make_client)
    photo = upload_photo(c, alice)
    made = post(c, alice, body([photo], notes="hello")).json()
    h = auth_headers(alice)
    c.post(f"{URL}/{made['id']}/analyze", headers=h)
    r = c.get(f"{URL}/{made['id']}/report", headers=h)
    assert r.status_code == 200
    body = r.text
    assert "<html" in body and "<style" in body and "@media print" in body
    assert "Hygiene inspection report" in body and "Main kitchen" in body
    assert "What this report cannot establish" in body
    assert "Pathogen presence" in body
    assert "not an official inspection" in body
    # No inline <script> or external assets (self-contained).
    assert "<script" not in body.lower() and "http://" not in body.replace("https://", "").lower()
    # Owner-only.
    bob = register_user(c, "bob@example.com")
    assert c.get(f"{URL}/{made['id']}/report", headers=auth_headers(bob)).status_code == 404


def test_csv_export_is_not_offered(make_client: Make) -> None:
    """No CSV endpoint exists (no accidental data export)."""
    c, alice, _, _ = world(make_client)
    photo = upload_photo(c, alice)
    made = post(c, alice, body([photo])).json()
    assert c.get(f"{URL}/{made['id']}.csv", headers=auth_headers(alice)).status_code == 404


# ---------------- validation ----------------
@pytest.mark.parametrize("over", [
    {"location_name": "   "},
    {"location_name": "x" * 121},
    {"location_type": "spaceship"},
    {"notes": "x" * 2001},
    {"media_ids": ["not-a-uuid"]},
])
def test_create_validation(make_client: Make, over: dict[str, Any]) -> None:
    c, alice, _, _ = world(make_client)
    photo = upload_photo(c, alice)
    assert post(c, alice, {**body([photo]), **over}).status_code == 422


def test_writes_require_csrf_header(make_client: Make) -> None:
    c, alice, _, _ = world(make_client)
    h = {"Authorization": f"Bearer {alice}"}
    photo = upload_photo(c, alice)
    assert c.post(URL, headers=h, json=body([photo])).status_code == 403
    made = post(c, alice, body([photo])).json()
    assert c.post(f"{URL}/{made['id']}/analyze", headers=h).status_code == 403
    assert c.post(f"{URL}/{made['id']}/submit", headers=h).status_code == 403
    assert c.delete(f"{URL}/{made['id']}", headers=h).status_code == 403