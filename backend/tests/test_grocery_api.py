from app.api.deps import get_text_factory
from tests.conftest import auth_headers, register_user
from tests.test_meal_plan_api import FakeText, _good_plan, _install
from collections.abc import Callable
from fastapi.testclient import TestClient
import json

Make = Callable[..., TestClient]


def _plan_with(c: TestClient, tok: str) -> dict:
    body = _good_plan()
    return c.post(
        "/api/v1/meal-plans/blank",
        headers=auth_headers(tok),
        json={"week_start_date": "2026-11-02"},
    ).json()


def _world(make_client: Make) -> tuple[TestClient, str, str]:
    c = make_client(
        allow_external_ai_providers=True, text_provider="openai_compatible",
        text_api_base_url="https://api.example.com/v1", text_api_model="m",
    )
    _install(c, FakeText(raw=json.dumps(_good_plan())))
    return c, register_user(c, "a@example.com"), register_user(c, "b@example.com")


def _custom_plan(c: TestClient, tok: str, ingredients: list[dict]) -> dict:
    plan = c.post(
        "/api/v1/meal-plans/blank",
        headers=auth_headers(tok),
        json={"week_start_date": "2026-11-02"},
    ).json()
    days = plan["plan"]["days"]
    days[0]["meals"][0]["title"] = "Rice bowl"
    days[0]["meals"][0]["ingredients"] = ingredients
    r = c.put(
        f"/api/v1/meal-plans/{plan['id']}",
        headers=auth_headers(tok),
        json={
            "title": "Test",
            "week_start_date": "2026-11-02",
            "days": days,
        },
    )
    return r.json()


def test_create_from_plan_merges_ingredients(make_client: Make) -> None:
    c, tok, _ = _world(make_client)
    plan = _custom_plan(
        c, tok,
        [
            {"name": "rice", "quantity": 100, "unit": "g"},
            {"name": "Rice", "quantity": 1, "unit": "kg"},
        ],
    )
    r = c.post(
        "/api/v1/grocery-lists",
        headers=auth_headers(tok),
        json={"plan_id": plan["id"]},
    )
    assert r.status_code == 201, r.text
    items = r.json()["items"]
    assert len(items) == 1
    assert items[0]["name"].lower() == "rice"
    assert items[0]["unit"] == "kg"
    assert abs(items[0]["quantity"] - 1.1) < 0.01


def test_create_from_plan_keeps_unrelated_units_apart(make_client: Make) -> None:
    c, tok, _ = _world(make_client)
    plan = _custom_plan(
        c, tok,
        [
            {"name": "salt", "quantity": 5, "unit": "g"},
            {"name": "salt", "quantity": 2, "unit": "tsp"},
        ],
    )
    r = c.post(
        "/api/v1/grocery-lists",
        headers=auth_headers(tok),
        json={"plan_id": plan["id"]},
    )
    items = r.json()["items"]
    assert sorted(i["unit"] for i in items) == ["g", "tsp"]


def test_edit_checked_and_delete_items(make_client: Make) -> None:
    c, tok, _ = _world(make_client)
    plan = _custom_plan(
        c, tok,
        [{"name": "rice", "quantity": 100, "unit": "g"}],
    )
    gl = c.post(
        "/api/v1/grocery-lists",
        headers=auth_headers(tok),
        json={"plan_id": plan["id"]},
    ).json()
    # check the item
    body = {
        "title": gl["title"],
        "items": [
            {
                "name": gl["items"][0]["name"],
                "quantity": 200,
                "unit": gl["items"][0]["unit"],
                "checked": True,
            }
        ],
        "expected_revision": 1,
    }
    r = c.put(
        f"/api/v1/grocery-lists/{gl['id']}", headers=auth_headers(tok), json=body
    )
    assert r.status_code == 200
    out = r.json()
    assert out["items"][0]["checked"] is True
    assert out["items"][0]["quantity"] == 200
    assert out["revision"] == 2


def test_revision_conflict(make_client: Make) -> None:
    c, tok, _ = _world(make_client)
    plan = _custom_plan(c, tok, [{"name": "rice", "quantity": 100, "unit": "g"}])
    gl = c.post(
        "/api/v1/grocery-lists",
        headers=auth_headers(tok),
        json={"plan_id": plan["id"]},
    ).json()
    body = {"title": gl["title"], "items": gl["items"], "expected_revision": 1}
    c.put(f"/api/v1/grocery-lists/{gl['id']}", headers=auth_headers(tok), json=body)
    stale = c.put(
        f"/api/v1/grocery-lists/{gl['id']}", headers=auth_headers(tok),
        json={**body, "expected_revision": 1},
    )
    assert stale.status_code == 409


def test_ownership_isolation(make_client: Make) -> None:
    c, alice, bob = _world(make_client)
    plan = _custom_plan(c, alice, [{"name": "rice", "quantity": 100, "unit": "g"}])
    gl = c.post(
        "/api/v1/grocery-lists",
        headers=auth_headers(alice),
        json={"plan_id": plan["id"]},
    ).json()
    assert c.get(f"/api/v1/grocery-lists/{gl['id']}", headers=auth_headers(bob)).status_code == 404
    assert c.delete(f"/api/v1/grocery-lists/{gl['id']}", headers=auth_headers(bob)).status_code == 404


def test_create_from_foreign_plan_is_404(make_client: Make) -> None:
    c, alice, bob = _world(make_client)
    plan = _custom_plan(c, alice, [{"name": "rice", "quantity": 100, "unit": "g"}])
    r = c.post(
        "/api/v1/grocery-lists",
        headers=auth_headers(bob),
        json={"plan_id": plan["id"]},
    )
    assert r.status_code == 404


def test_deleting_plan_keeps_list_with_null_plan_link(make_client: Make) -> None:
    c, tok, _ = _world(make_client)
    plan = _custom_plan(c, tok, [{"name": "rice", "quantity": 100, "unit": "g"}])
    gl = c.post(
        "/api/v1/grocery-lists",
        headers=auth_headers(tok),
        json={"plan_id": plan["id"]},
    ).json()
    c.delete(f"/api/v1/meal-plans/{plan['id']}", headers=auth_headers(tok))
    after = c.get(
        f"/api/v1/grocery-lists/{gl['id']}", headers=auth_headers(tok)
    ).json()
    assert after["plan_id"] is None and after["items"]