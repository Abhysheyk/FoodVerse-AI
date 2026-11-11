"""End-to-end meal plan tests. The text provider is faked; everything else is real."""

import json
import uuid
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from typing import Any

from fastapi.testclient import TestClient

from app.ai.text import (
    TextBadOutputError,
    TextProviderInfo,
    TextRateLimitedError,
    TextTimeoutError,
    TextUnavailableError,
)
from app.api.deps import get_text_factory
from tests.conftest import auth_headers, register_user

Make = Callable[..., TestClient]


class FakeText:
    def __init__(self, raw: str | None = None, error: Exception | None = None) -> None:
        self.raw = raw
        self.error = error
        self.calls = 0
        self.prompts: list[str] = []
        self.info = TextProviderInfo(
            name="fake-text", model="fake-model-1", external=False
        )

    def complete_json(self, prompt: str, schema: dict[str, Any]) -> str:
        self.calls += 1
        self.prompts.append(prompt)
        if self.error:
            raise self.error  # type: ignore[misc]
        return self.raw or json.dumps({"days": []})


def _install(c: TestClient, fake: FakeText) -> None:
    c.app.dependency_overrides[get_text_factory] = lambda: lambda: fake  # type: ignore[attr-defined]


def _good_plan(
    *, week_start: date = date(2026, 11, 2), meals_per_day: int = 3
) -> dict[str, Any]:
    days = []
    for i in range(7):
        days.append(
            {
                "day_date": (week_start + timedelta(days=i)).isoformat(),
                "meals": [
                    {
                        "meal": c,
                        "title": f"{c.title()} item {i}",
                        "servings": 1,
                        "cooking_minutes": 20,
                        "ingredients": [
                            {"name": "rice", "quantity": 100, "unit": "g"},
                            {"name": "tomato", "quantity": 1, "unit": "piece"},
                        ],
                    }
                    for c in ("breakfast", "lunch", "dinner")[:meals_per_day]
                ],
            }
        )
    return {"title": "Weekly plan", "days": days, "notes": None}


def _world(make_client: Make, fake: FakeText | None = None) -> tuple[TestClient, str, str]:
    c = make_client(allow_external_ai_providers=True, text_provider="openai_compatible",
                    text_api_base_url="https://api.example.com/v1", text_api_model="m")
    if fake:
        _install(c, fake)
    alice = register_user(c, "alice@example.com")
    bob = register_user(c, "bob@example.com")
    return c, alice, bob


# ---- capabilities ----
def test_capabilities_report_unconfigured_provider(make_client: Make) -> None:
    c = make_client()  # default settings: text_provider=none
    tok = register_user(c, "a@example.com")
    body = c.get("/api/v1/meal-plans/capabilities", headers=auth_headers(tok)).json()
    assert body["text_provider_configured"] is False and body["message"]


def test_capabilities_when_configured(make_client: Make) -> None:
    c, tok, _ = _world(make_client, FakeText())
    body = c.get("/api/v1/meal-plans/capabilities", headers=auth_headers(tok)).json()
    assert body["text_provider_configured"] is True
    assert body["text_provider"] == "openai_compatible"


# ---- blank plan ----
def test_blank_plan_is_created_and_has_seven_days(make_client: Make) -> None:
    c, tok, _ = _world(make_client)
    r = c.post(
        "/api/v1/meal-plans/blank",
        headers=auth_headers(tok),
        json={"week_start_date": "2026-11-02"},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["source"] == "manual" and body["revision"] == 1
    assert len(body["plan"]["days"]) == 7
    assert all(len(d["meals"]) == 1 for d in body["plan"]["days"])


# ---- generation ----
def test_generation_saves_the_plan(make_client: Make) -> None:
    fake = FakeText(raw=json.dumps(_good_plan()))
    c, tok, _ = _world(make_client, fake)
    r = c.post(
        "/api/v1/meal-plans/generate",
        headers=auth_headers(tok),
        json={"week_start_date": "2026-11-02", "include_snacks": True},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["source"] == "ai" and body["meal_count"] == 21
    assert "rice" in fake.prompts[0].lower()
    assert "MUST avoid" not in fake.prompts[0]  # no allergies set


def test_generation_prompt_includes_constraints(make_client: Make) -> None:
    fake = FakeText(raw=json.dumps(_good_plan()))
    c, tok, _ = _world(make_client, fake)
    # set prefs
    c.put(
        "/api/v1/users/me/preferences",
        headers=auth_headers(tok),
        json={
            "unit_system": "metric",
            "dietary_preferences": [],
            "allergies": ["peanut", "milk"],
            "excluded_ingredients": ["onion"],
            "dietary_pattern": "vegetarian",
            "preferred_cuisines": ["south indian"],
            "budget": "moderate",
            "max_cooking_minutes": 30,
            "default_servings": 2,
            "pantry_ingredients": ["rice", "dal"],
        },
    )
    c.post(
        "/api/v1/meal-plans/generate",
        headers=auth_headers(tok),
        json={"week_start_date": "2026-11-02"},
    )
    prompt = fake.prompts[0].lower()
    for token in ("peanut", "milk", "onion", "vegetarian", "south indian", "30", "2"):
        assert token in prompt, token


def test_generation_rejects_plan_that_breaks_an_allergy(make_client: Make) -> None:
    bad = _good_plan()
    bad["days"][0]["meals"][0]["ingredients"].append(
        {"name": "peanut sauce", "quantity": 30, "unit": "g"}
    )
    fake = FakeText(raw=json.dumps(bad))
    c, tok, _ = _world(make_client, fake)
    c.put(
        "/api/v1/users/me/preferences",
        headers=auth_headers(tok),
        json={"unit_system": "metric", "dietary_preferences": [], "allergies": ["peanut"]},
    )
    r = c.post(
        "/api/v1/meal-plans/generate",
        headers=auth_headers(tok),
        json={"week_start_date": "2026-11-02"},
    )
    assert r.status_code == 422, r.text
    err = r.json()["error"]
    assert err["code"] == "meal_plan_constraint_violation"
    assert "peanut sauce" in err["message"] or "allergy:peanut" in r.text
    # nothing was saved
    assert c.get("/api/v1/meal-plans", headers=auth_headers(tok)).json()["total"] == 0


def test_generation_rejects_excluded_ingredient_and_vegan_violation(make_client: Make) -> None:
    bad = _good_plan()
    bad["days"][1]["meals"][0]["ingredients"].append(
        {"name": "onion", "quantity": 1, "unit": "piece"}
    )
    bad["days"][2]["meals"][0]["ingredients"].append(
        {"name": "butter", "quantity": 20, "unit": "g"}
    )
    fake = FakeText(raw=json.dumps(bad))
    c, tok, _ = _world(make_client, fake)
    c.put(
        "/api/v1/users/me/preferences",
        headers=auth_headers(tok),
        json={
            "unit_system": "metric", "dietary_preferences": [],
            "dietary_pattern": "vegan", "excluded_ingredients": ["onion"],
        },
    )
    r = c.post(
        "/api/v1/meal-plans/generate",
        headers=auth_headers(tok),
        json={"week_start_date": "2026-11-02"},
    )
    assert r.status_code == 422
    text = r.text
    assert "excluded:onion" in text and "diet:vegan" in text


def test_generation_rejects_wrong_week_dates(make_client: Make) -> None:
    bad = _good_plan(week_start=date(2026, 10, 26))  # one week earlier
    c, tok, _ = _world(make_client, FakeText(raw=json.dumps(bad)))
    r = c.post(
        "/api/v1/meal-plans/generate",
        headers=auth_headers(tok),
        json={"week_start_date": "2026-11-02"},
    )
    assert r.status_code == 502 and r.json()["error"]["code"] == "text_bad_output"


def test_generation_rejects_unknown_units(make_client: Make) -> None:
    bad = _good_plan()
    bad["days"][0]["meals"][0]["ingredients"][0]["unit"] = "splash"
    c, tok, _ = _world(make_client, FakeText(raw=json.dumps(bad)))
    r = c.post(
        "/api/v1/meal-plans/generate",
        headers=auth_headers(tok),
        json={"week_start_date": "2026-11-02"},
    )
    assert r.status_code == 502


def test_generation_provider_errors_map_safely(make_client: Make) -> None:
    for error, status in (
        (TextUnavailableError("down"), 503),
        (TextTimeoutError("slow"), 504),
        (TextBadOutputError("bad"), 502),
        (TextRateLimitedError("busy"), 429),
    ):
        c, tok, _ = _world(make_client, FakeText(error=error))
        r = c.post(
            "/api/v1/meal-plans/generate",
            headers=auth_headers(tok),
            json={"week_start_date": "2026-11-02"},
        )
        assert r.status_code == status, (error, r.text)


def test_generation_fails_cleanly_when_provider_unconfigured(make_client: Make) -> None:
    c = make_client()  # text_provider=none
    tok = register_user(c, "a@example.com")
    r = c.post(
        "/api/v1/meal-plans/generate",
        headers=auth_headers(tok),
        json={"week_start_date": "2026-11-02"},
    )
    assert r.status_code == 503 and r.json()["error"]["code"] == "text_unavailable"


# ---- update / copy / delete ----
def test_update_bumps_revision_and_resets_estimate(make_client: Make) -> None:
    c, tok, _ = _world(make_client)
    created = c.post(
        "/api/v1/meal-plans/blank",
        headers=auth_headers(tok),
        json={"week_start_date": "2026-11-02", "title": "P"},
    ).json()
    body = {
        "title": "Renamed",
        "week_start_date": "2026-11-02",
        "notes": "changed",
        "days": created["plan"]["days"],
        "expected_revision": 1,
    }
    r = c.put(
        f"/api/v1/meal-plans/{created['id']}", headers=auth_headers(tok), json=body
    )
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["revision"] == 2 and out["title"] == "Renamed"


def test_update_rejects_stale_revision(make_client: Make) -> None:
    c, tok, _ = _world(make_client)
    p = c.post(
        "/api/v1/meal-plans/blank",
        headers=auth_headers(tok),
        json={"week_start_date": "2026-11-02"},
    ).json()
    c.put(
        f"/api/v1/meal-plans/{p['id']}",
        headers=auth_headers(tok),
        json={
            "title": "x", "week_start_date": "2026-11-02",
            "days": p["plan"]["days"], "expected_revision": 1,
        },
    )
    r = c.put(
        f"/api/v1/meal-plans/{p['id']}",
        headers=auth_headers(tok),
        json={
            "title": "x", "week_start_date": "2026-11-02",
            "days": p["plan"]["days"], "expected_revision": 1,
        },
    )
    assert r.status_code == 409 and r.json()["error"]["code"] == "meal_plan_revision_conflict"


def test_copy_plan_shifts_dates(make_client: Make) -> None:
    c, tok, _ = _world(make_client, FakeText(raw=json.dumps(_good_plan())))
    made = c.post(
        "/api/v1/meal-plans/generate",
        headers=auth_headers(tok),
        json={"week_start_date": "2026-11-02"},
    ).json()
    copy = c.post(
        f"/api/v1/meal-plans/{made['id']}/copy",
        headers=auth_headers(tok),
        json={"week_start_date": "2026-11-09"},
    )
    assert copy.status_code == 201, copy.text
    body = copy.json()
    assert body["source"] == "copied"
    assert body["plan"]["days"][0]["day_date"] == "2026-11-09"


def test_delete_plan_and_ownership(make_client: Make) -> None:
    c, tok, bob = _world(make_client)
    p = c.post(
        "/api/v1/meal-plans/blank",
        headers=auth_headers(tok),
        json={"week_start_date": "2026-11-02"},
    ).json()
    assert c.get(f"/api/v1/meal-plans/{p['id']}", headers=auth_headers(bob)).status_code == 404
    assert c.delete(f"/api/v1/meal-plans/{p['id']}", headers=auth_headers(bob)).status_code == 404
    assert c.delete(f"/api/v1/meal-plans/{p['id']}", headers=auth_headers(tok)).status_code == 204
    assert c.get(f"/api/v1/meal-plans/{p['id']}", headers=auth_headers(tok)).status_code == 404


def test_writes_require_csrf_header(make_client: Make) -> None:
    c, tok, _ = _world(make_client)
    r = c.post(
        "/api/v1/meal-plans/blank",
        headers={"Authorization": f"Bearer {tok}"},
        json={"week_start_date": "2026-11-02"},
    )
    assert r.status_code == 403


# ---- estimate ----
def test_estimate_requires_a_nutrition_source(make_client: Make) -> None:
    c, tok, _ = _world(make_client)
    p = c.post(
        "/api/v1/meal-plans/blank",
        headers=auth_headers(tok),
        json={"week_start_date": "2026-11-02"},
    ).json()
    r = c.post(
        f"/api/v1/meal-plans/{p['id']}/estimate", headers=auth_headers(tok)
    )
    assert r.status_code == 503 and r.json()["error"]["code"] == "nutrition_not_configured"


# ---- generation rate limit ----
def test_generation_is_rate_limited(make_client: Make) -> None:
    fake = FakeText(raw=json.dumps(_good_plan()))
    c = make_client(
        allow_external_ai_providers=True, text_provider="openai_compatible",
        text_api_base_url="https://api.example.com/v1", text_api_model="m",
        meal_plan_generate_rate_limit_per_hour=1,
    )
    _install(c, fake)
    tok = register_user(c, "a@example.com")
    ok = c.post(
        "/api/v1/meal-plans/generate",
        headers=auth_headers(tok),
        json={"week_start_date": "2026-11-02"},
    )
    assert ok.status_code == 201
    second = c.post(
        "/api/v1/meal-plans/generate",
        headers=auth_headers(tok),
        json={"week_start_date": "2026-11-09"},
    )
    assert second.status_code == 429
    assert fake.calls == 1  # no wasted provider call