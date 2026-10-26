import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi.testclient import TestClient

from app.ai.vision import DetectedFood
from tests.conftest import auth_headers, register_user
from tests.food_helpers import FakeVision, install, search_food, upload_photo, usda_food, weight

Make = Callable[..., TestClient]


def now_iso(hours_ago: float = 1) -> str:
    return (datetime.now(UTC) - timedelta(hours=hours_ago)).isoformat()


def world(make_client: Make, **kw: Any) -> tuple[TestClient, str, str]:
    c = make_client()
    install(c, usda=[usda_food()], **kw)
    return c, register_user(c, "alice@example.com"), register_user(c, "bob@example.com")


def body(ref: str | None, grams: float = 150, **extra: Any) -> dict[str, Any]:
    item: dict[str, Any] = {"name": "Apple", "portion": weight(grams)}
    if ref:
        item["food_ref"] = ref
    return {"items": [item], "eaten_at": now_iso(), "category": "snack", **extra}


def save(c: TestClient, tok: str, payload: dict[str, Any]) -> dict[str, Any]:
    r = c.post("/api/v1/meals", headers=auth_headers(tok), json=payload)
    assert r.status_code == 201, r.text
    return dict(r.json())


def test_save_persists_full_audit_and_server_side_totals(make_client: Make) -> None:
    c, alice, _ = world(make_client)
    ref = search_food(c, alice)[0]["food_ref"]
    meal = save(c, alice, body(ref, notes="  lunch box  "))
    assert meal["revision"] == 1 and meal["notes"] == "lunch box" and meal["category"] == "snack"
    assert meal["calories"] == {"low": 78.0, "high": 78.0, "complete": True}
    audit = meal["result"]
    assert audit["items"][0]["food"]["source"] == "usda_fdc"
    assert audit["items"][0]["food"]["per_100g"]["energy_kcal"] == 52.0
    assert audit["method"] and audit["unit_basis"] and audit["disclaimer"]
    again = c.get(f"/api/v1/meals/{meal['id']}", headers=auth_headers(alice)).json()
    assert again["result"] == audit


def test_client_cannot_supply_totals(make_client: Make) -> None:
    c, alice, _ = world(make_client)
    payload = body(None)
    payload["totals"] = {"energy_kcal": {"low": 1, "high": 1}}
    assert c.post("/api/v1/meals", headers=auth_headers(alice), json=payload).status_code == 422
    payload = body(None)
    payload["items"][0]["per_100g"] = {"energy_kcal": 1}
    assert c.post("/api/v1/meals", headers=auth_headers(alice), json=payload).status_code == 422


def test_meal_without_nutrition_data_is_saved_honestly(make_client: Make) -> None:
    c, alice, _ = world(make_client)
    meal = save(c, alice, body(None))
    assert meal["calories"] == {"low": None, "high": None, "complete": False}
    assert "no_nutrition_data" in meal["result"]["items"][0]["warnings"]


def test_save_creates_history_entry_and_delete_removes_it(make_client: Make) -> None:
    c, alice, _ = world(make_client)
    meal = save(c, alice, body(None))
    h = auth_headers(alice)
    hist = c.get("/api/v1/history?module=food_recognition", headers=h).json()
    assert hist["total"] == 1 and hist["items"][0]["id"] == meal["id"]
    assert c.delete(f"/api/v1/meals/{meal['id']}", headers=h).status_code == 204
    assert c.get(f"/api/v1/meals/{meal['id']}", headers=h).status_code == 404
    assert c.get("/api/v1/history", headers=h).json()["total"] == 0
    assert c.get("/api/v1/meals", headers=h).json()["total"] == 0


def test_deleting_through_history_removes_the_meal_too(make_client: Make) -> None:
    c, alice, _ = world(make_client)
    meal = save(c, alice, body(None))
    h = auth_headers(alice)
    assert c.delete(f"/api/v1/history/{meal['id']}", headers=h).status_code == 204
    assert c.get("/api/v1/meals", headers=h).json()["total"] == 0


def test_ownership_isolation(make_client: Make) -> None:
    c, alice, bob = world(make_client)
    meal = save(c, alice, body(None))
    hb = auth_headers(bob)
    mid = meal["id"]
    assert c.get(f"/api/v1/meals/{mid}", headers=hb).status_code == 404
    assert c.put(f"/api/v1/meals/{mid}", headers=hb, json=body(None)).status_code == 404
    assert c.delete(f"/api/v1/meals/{mid}", headers=hb).status_code == 404
    assert c.get("/api/v1/meals", headers=hb).json() == {
        "items": [],
        "total": 0,
        "page": 1,
        "page_size": 10,
        "pages": 0,
    }
    assert (
        c.get(f"/api/v1/meals/{mid}", headers=auth_headers(alice)).status_code == 200
    )  # untouched
    assert c.get(f"/api/v1/meals/{uuid.uuid4()}", headers=hb).status_code == 404


def test_cannot_attach_someone_elses_photo(make_client: Make) -> None:
    c, alice, bob = world(make_client)
    photo = upload_photo(c, alice)
    r = c.post("/api/v1/meals", headers=auth_headers(bob), json=body(None, media_id=photo))
    assert r.status_code == 404
    assert c.get("/api/v1/meals", headers=auth_headers(bob)).json()["total"] == 0


def test_scan_audit_keeps_model_output_labelled_and_links_photo(make_client: Make) -> None:
    c, alice, _ = world(
        make_client, vision=FakeVision([DetectedFood(name="Apple", ambiguous=True)])
    )
    photo = upload_photo(c, alice)
    scan = c.post("/api/v1/food/scan", headers=auth_headers(alice), json={"media_id": photo}).json()
    ref = search_food(c, alice)[0]["food_ref"]
    payload = body(ref, scan_ref=scan["scan_ref"])
    payload["items"][0]["observed_id"] = 0
    meal = save(c, alice, payload)
    assert meal["media_id"] == photo
    obs = meal["result"]["model_observations"]
    assert obs["items"][0]["name"] == "Apple" and obs["provider"]["model"] == "fake-vision-1"
    assert meal["result"]["items"][0]["origin"] == "model"
    # deleting the photo keeps the meal and its audit
    assert c.delete(f"/api/v1/media/{photo}", headers=auth_headers(alice)).status_code == 204
    kept = c.get(f"/api/v1/meals/{meal['id']}", headers=auth_headers(alice)).json()
    assert kept["media_id"] is None and kept["result"]["model_observations"]


def test_update_recomputes_and_bumps_revision(make_client: Make) -> None:
    c, alice, _ = world(make_client)
    h = auth_headers(alice)
    ref = search_food(c, alice)[0]["food_ref"]
    meal = save(c, alice, body(ref, 100))
    item_id = meal["result"]["items"][0]["item_id"]
    edit = body(None, 300, expected_revision=1)
    edit["items"][0]["item_id"] = item_id  # keeps the chosen food, changes the portion only
    edit["category"] = "dinner"
    r = c.put(f"/api/v1/meals/{meal['id']}", headers=h, json=edit)
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["revision"] == 2 and out["category"] == "dinner"
    assert out["calories"]["low"] == 156.0
    assert out["result"]["items"][0]["food"]["source_id"] == "171688"
    hist = c.get(f"/api/v1/history/{meal['id']}", headers=h).json()
    assert hist["title"].startswith("Dinner")


def test_update_can_clear_food_and_rename(make_client: Make) -> None:
    c, alice, _ = world(make_client)
    ref = search_food(c, alice)[0]["food_ref"]
    meal = save(c, alice, body(ref))
    edit = body(None)
    edit["items"][0].update(
        item_id=meal["result"]["items"][0]["item_id"], clear_food=True, name="Mystery"
    )
    out = c.put(f"/api/v1/meals/{meal['id']}", headers=auth_headers(alice), json=edit).json()
    item = out["result"]["items"][0]
    assert item["food"] is None and item["nutrients"] == {} and out["calories"]["low"] is None
    assert item["origin"] == "user_added" and item["name"] == "Mystery"


def test_update_rejects_foreign_item_ids_and_stale_revision(make_client: Make) -> None:
    c, alice, _ = world(make_client)
    h = auth_headers(alice)
    meal = save(c, alice, body(None))
    other = save(c, alice, body(None))
    bad = body(None)
    bad["items"][0]["item_id"] = other["result"]["items"][0]["item_id"]
    assert c.put(f"/api/v1/meals/{meal['id']}", headers=h, json=bad).status_code == 422
    ok = c.put(f"/api/v1/meals/{meal['id']}", headers=h, json=body(None, expected_revision=1))
    assert ok.status_code == 200
    stale = c.put(f"/api/v1/meals/{meal['id']}", headers=h, json=body(None, expected_revision=1))
    assert stale.status_code == 409 and stale.json()["error"]["code"] == "meal_revision_conflict"


def test_list_filters_pagination_and_order(make_client: Make) -> None:
    c, alice, _ = world(make_client)
    h = auth_headers(alice)
    for i, cat in enumerate(["breakfast", "lunch", "lunch", "dinner", "snack"]):
        p = body(None)
        p["category"], p["eaten_at"] = cat, now_iso(hours_ago=10 - i)
        save(c, alice, p)
    page = c.get("/api/v1/meals?page_size=2", headers=h).json()
    assert (page["total"], page["pages"], len(page["items"])) == (5, 3, 2)
    assert page["items"][0]["category"] == "snack"  # newest eaten_at first
    lunch = c.get("/api/v1/meals?category=lunch", headers=h).json()
    assert lunch["total"] == 2
    cutoff = now_iso(hours_ago=7.5)
    recent = c.get("/api/v1/meals", headers=h, params={"date_from": cutoff}).json()
    assert recent["total"] == 2  # the 7 h and 6 h old meals
    assert (
        c.get(
            "/api/v1/meals", headers=h, params={"date_from": now_iso(1), "date_to": now_iso(5)}
        ).status_code
        == 422
    )
    for q in ("category=brunch", "page=0", "page_size=101"):
        assert c.get(f"/api/v1/meals?{q}", headers=h).status_code == 422


def test_write_validation(make_client: Make) -> None:
    c, alice, _ = world(make_client)
    h = auth_headers(alice)

    def post(**over: Any) -> int:
        status: int = c.post("/api/v1/meals", headers=h, json={**body(None), **over}).status_code
        return status

    assert post(eaten_at="2026-01-01T12:00:00") == 422  # no timezone
    assert post(eaten_at=(datetime.now(UTC) + timedelta(days=3)).isoformat()) == 422
    assert post(eaten_at="1990-01-01T00:00:00+00:00") == 422
    assert post(category="brunch") == 422
    assert post(notes="x" * 1001) == 422
    assert post(items=[]) == 422
    assert post(media_id="not-a-uuid") == 422
    no_csrf = c.post("/api/v1/meals", headers={"Authorization": f"Bearer {alice}"}, json=body(None))
    assert no_csrf.status_code == 403
