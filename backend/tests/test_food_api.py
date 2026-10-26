from collections.abc import Callable
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from app.ai.vision import (
    DetectedFood,
    VisionBadOutputError,
    VisionRateLimitedError,
    VisionTimeoutError,
    VisionUnavailableError,
)
from tests.conftest import CSRF, auth_headers, register_user
from tests.food_helpers import (
    FakeVision,
    calc,
    install,
    new_id,
    off_product,
    search_food,
    upload_photo,
    usda_food,
    weight,
)

Make = Callable[..., TestClient]
APPLE = usda_food()


def setup(make_client: Make, **kw: Any) -> tuple[TestClient, str]:
    c = make_client(**kw.pop("settings", {}))
    install(c, **kw)
    return c, register_user(c, f"alice-{new_id()[:8]}@example.com")


def ready(make_client: Make, **kw: Any) -> tuple[TestClient, str]:
    return setup(make_client, usda=[APPLE], **kw)


# ---------------- capabilities ----------------
def test_capabilities_say_what_is_not_configured(make_client: Make) -> None:
    c = make_client()
    install(c, use_usda=False)
    tok = register_user(c, "a@example.com")
    body = c.get("/api/v1/food/capabilities", headers=auth_headers(tok)).json()
    assert body["vision"]["configured"] is False and body["vision"]["message"]
    assert body["nutrition"]["any_configured"] is False
    states = {s["source"]: s["status"] for s in body["nutrition"]["sources"]}
    assert states["usda_fdc"] == "not_configured" and states["open_food_facts"] == "not_configured"


def test_capabilities_when_configured_never_expose_secrets(make_client: Make) -> None:
    c, tok = setup(
        make_client,
        usda=[APPLE],
        settings={"ollama_enabled": True, "ollama_vision_model": "llava-test"},
    )
    r = c.get("/api/v1/food/capabilities", headers=auth_headers(tok))
    assert r.json()["vision"] == {
        "configured": True,
        "provider": "ollama",
        "model": "llava-test",
        "external": False,
        "message": None,
    }
    assert "test-usda-key" not in r.text
    states = {s["source"]: s["status"] for s in r.json()["nutrition"]["sources"]}
    assert states["usda_fdc"] != "not_configured"


def test_food_endpoints_require_auth(client: TestClient) -> None:
    for method, path in (
        ("get", "/api/v1/food/capabilities"),
        ("post", "/api/v1/food/scan"),
        ("post", "/api/v1/food/calculate"),
        ("get", "/api/v1/nutrition/search?q=apple"),
        ("get", "/api/v1/meals"),
        ("post", "/api/v1/meals"),
        ("get", f"/api/v1/meals/{new_id()}"),
    ):
        assert getattr(client, method)(path, headers=CSRF).status_code == 401, path


# ---------------- scan ----------------
def test_scan_returns_only_validated_names_no_numbers(make_client: Make) -> None:
    fake = FakeVision(
        [DetectedFood(name="Apple", description="red", ambiguous=True, alternatives=["Pear"])]
    )
    c, tok = ready(make_client, vision=fake)
    media = upload_photo(c, tok)
    r = c.post("/api/v1/food/scan", headers=auth_headers(tok), json={"media_id": media})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["items"] == [
        {
            "observed_id": 0,
            "name": "Apple",
            "description": "red",
            "ambiguous": True,
            "alternatives": ["Pear"],
        }
    ]
    assert body["scan_ref"] and body["uncertainty_note"]
    flat = r.text.lower()
    assert "confidence" not in flat.replace("confidence score", "") and "calorie" not in flat
    assert (
        fake.calls == 1 and fake.images[0][:8] == b"\x89PNG\r\n\x1a\n"
    )  # a real image reached the model


def test_scan_empty_result_is_honest(make_client: Make) -> None:
    c, tok = ready(make_client, vision=FakeVision([]))
    r = c.post(
        "/api/v1/food/scan", headers=auth_headers(tok), json={"media_id": upload_photo(c, tok)}
    )
    assert r.status_code == 200 and r.json()["items"] == []


def test_scan_when_vision_not_configured(make_client: Make) -> None:
    c, tok = ready(make_client)  # real factory: OLLAMA disabled
    r = c.post(
        "/api/v1/food/scan", headers=auth_headers(tok), json={"media_id": upload_photo(c, tok)}
    )
    assert r.status_code == 503 and r.json()["error"]["code"]


@pytest.mark.parametrize(
    ("error", "status"),
    [
        (VisionUnavailableError("down"), 503),
        (VisionTimeoutError("slow"), 504),
        (VisionBadOutputError("bad"), 502),
        (VisionRateLimitedError("busy"), 429),
    ],
)
def test_scan_model_failures_map_to_safe_errors(
    make_client: Make, error: Exception, status: int
) -> None:
    c, tok = ready(make_client, vision=FakeVision(error=error))  # type: ignore[arg-type]
    r = c.post(
        "/api/v1/food/scan", headers=auth_headers(tok), json={"media_id": upload_photo(c, tok)}
    )
    assert r.status_code == status
    assert set(r.json()["error"]) >= {"code", "message", "request_id"} and "items" not in r.json()


def test_scan_ownership_unknown_and_csrf(make_client: Make) -> None:
    fake = FakeVision([DetectedFood(name="Apple")])
    c, alice = ready(make_client, vision=fake)
    bob = register_user(c, "bob@example.com")
    media = upload_photo(c, alice)
    assert (
        c.post("/api/v1/food/scan", headers=auth_headers(bob), json={"media_id": media}).status_code
        == 404
    )
    assert (
        c.post(
            "/api/v1/food/scan", headers=auth_headers(alice), json={"media_id": new_id()}
        ).status_code
        == 404
    )
    no_csrf = c.post(
        "/api/v1/food/scan", headers={"Authorization": f"Bearer {alice}"}, json={"media_id": media}
    )
    assert no_csrf.status_code == 403 and fake.calls == 0  # model never reached


def test_scan_is_rate_limited_per_user(make_client: Make) -> None:
    fake = FakeVision([DetectedFood(name="Apple")])
    c, alice = ready(make_client, vision=fake, settings={"scan_rate_limit_per_minute": 2})
    media = upload_photo(c, alice)
    codes = [
        c.post(
            "/api/v1/food/scan", headers=auth_headers(alice), json={"media_id": media}
        ).status_code
        for _ in range(3)
    ]
    assert codes == [200, 200, 429] and fake.calls == 2
    bob = register_user(c, "bob@example.com")
    bm = upload_photo(c, bob)
    assert (
        c.post("/api/v1/food/scan", headers=auth_headers(bob), json={"media_id": bm}).status_code
        == 200
    )


# ---------------- nutrition search ----------------
def test_search_returns_signed_candidates_with_source_metadata(make_client: Make) -> None:
    c, tok = ready(make_client)
    results = search_food(c, tok)
    assert results[0]["name"] == "Apples, raw, with skin" and results[0]["food_ref"]
    assert results[0]["source"] == "usda_fdc" and results[0]["attribution"]
    assert results[0]["per_100g"]["energy_kcal"] == 52.0


def test_search_reports_each_source_status_and_partial_failure(make_client: Make) -> None:
    c, tok = setup(make_client, usda=[APPLE], off=lambda r: httpx.Response(429), use_off=True)
    body = c.get("/api/v1/nutrition/search?q=apple", headers=auth_headers(tok)).json()
    st = {s["source"]: s["status"] for s in body["sources"]}
    assert st["usda_fdc"] == "ok" and st["open_food_facts"] == "rate_limited"
    assert len(body["results"]) == 1  # USDA data still shown


def test_search_unknown_food_is_empty_not_invented(make_client: Make) -> None:
    c, tok = setup(make_client, usda=[])
    body = c.get("/api/v1/nutrition/search?q=zzzqqq", headers=auth_headers(tok)).json()
    assert body["results"] == [] and body["sources"][1]["status"] in ("ok", "not_configured")


def test_search_all_sources_down(make_client: Make) -> None:
    c, tok = setup(make_client, usda=lambda r: httpx.Response(500))
    r = c.get("/api/v1/nutrition/search?q=apple", headers=auth_headers(tok))
    assert r.status_code == 200 and r.json()["results"] == []
    assert any(s["status"] == "unavailable" for s in r.json()["sources"])


def test_search_validation_and_rate_limit(make_client: Make) -> None:
    c, tok = ready(make_client, settings={"nutrition_search_rate_limit_per_minute": 2})
    assert c.get("/api/v1/nutrition/search?q=a", headers=auth_headers(tok)).status_code == 422
    assert c.get("/api/v1/nutrition/search", headers=auth_headers(tok)).status_code == 422
    codes = [
        c.get("/api/v1/nutrition/search?q=apple", headers=auth_headers(tok)).status_code
        for _ in range(3)
    ]
    assert codes == [200, 200, 429]


def test_barcode_lookup(make_client: Make) -> None:
    c, tok = setup(make_client, usda=[], off=[off_product()], use_off=True)
    r = c.get("/api/v1/nutrition/barcode/5000112637922", headers=auth_headers(tok))
    assert r.status_code == 200 and r.json()["result"]["serving_grams"] == 30.0
    assert c.get("/api/v1/nutrition/barcode/abc", headers=auth_headers(tok)).status_code == 422
    c2, tok2 = setup(make_client, usda=[])
    off_off = c2.get(
        "/api/v1/nutrition/barcode/5000112637922",
        headers=auth_headers(register_user(c2, "z@example.com")),
    )
    assert (
        off_off.json()["result"] is None
        and off_off.json()["sources"][0]["status"] == "not_configured"
    )
    _ = tok2


# ---------------- calculate ----------------
def test_calculate_is_deterministic_from_source_values(make_client: Make) -> None:
    c, tok = ready(make_client)
    ref = search_food(c, tok)[0]["food_ref"]
    r = calc(c, tok, [{"name": "Apple", "food_ref": ref, "portion": weight(150)}])
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["totals"]["energy_kcal"]["low"] == 78.0 == body["totals"]["energy_kcal"]["high"]
    assert body["totals"]["energy_kcal"]["complete"] is True
    assert body["totals"]["carbs_g"]["low"] == 20.7
    assert body["items"][0]["food"]["source_id"] == "171688"
    assert body["unit_basis"] and body["disclaimer"] and body["method"]
    assert (
        calc(c, tok, [{"name": "Apple", "food_ref": ref, "portion": weight(150)}]).json()["totals"]
        == body["totals"]
    )


def test_calculate_range_is_flagged_uncertain(make_client: Make) -> None:
    c, tok = ready(make_client)
    ref = search_food(c, tok)[0]["food_ref"]
    p = {"kind": "range", "min_amount": 100, "max_amount": 200, "unit": "g"}
    item = calc(c, tok, [{"name": "Apple", "food_ref": ref, "portion": p}]).json()["items"][0]
    assert item["portion"]["uncertain"] is True and "portion_is_estimate" in item["warnings"]
    assert (
        item["nutrients"]["energy_kcal"]["low"] == 52.0
        and item["nutrients"]["energy_kcal"]["high"] == 104.0
    )


def test_calculate_without_food_or_portion_gives_no_numbers(make_client: Make) -> None:
    c, tok = ready(make_client)
    ref = search_food(c, tok)[0]["food_ref"]
    r = calc(
        c,
        tok,
        [{"name": "Mystery stew", "portion": weight(200)}, {"name": "Apple", "food_ref": ref}],
    ).json()
    a, b = r["items"]
    assert a["nutrients"] == {} and "no_nutrition_data" in a["warnings"]
    assert b["nutrients"] == {} and "portion_missing" in b["warnings"]
    assert (
        r["totals"]["energy_kcal"]["low"] is None
        and r["totals"]["energy_kcal"]["complete"] is False
    )


def test_calculate_partial_nutrients_listed_not_zeroed(make_client: Make) -> None:
    c, tok = setup(make_client, usda=[usda_food(nutrients={"208": 52.0})])
    ref = search_food(c, tok)[0]["food_ref"]
    item = calc(c, tok, [{"name": "Apple", "food_ref": ref, "portion": weight(100)}]).json()[
        "items"
    ][0]
    assert "protein_g" not in item["nutrients"] and "protein_g" in item["not_reported"]
    assert "partial_nutrients" in item["warnings"]


def test_calculate_servings_need_source_serving_weight(make_client: Make) -> None:
    c, tok = setup(make_client, usda=[], off=[off_product()], use_off=True)
    ref = c.get("/api/v1/nutrition/search?q=biscuit", headers=auth_headers(tok)).json()["results"][
        0
    ]["food_ref"]
    two = {"kind": "servings", "count": 2}
    ok = calc(c, tok, [{"name": "Biscuit", "food_ref": ref, "portion": two}]).json()
    assert ok["items"][0]["portion"]["grams_low"] == 60.0
    assert ok["totals"]["energy_kcal"]["low"] == 270.0
    # a food whose source gives no serving weight cannot be measured in servings
    c2, tok2 = ready(make_client)
    ref2 = search_food(c2, tok2)[0]["food_ref"]
    r = calc(c2, tok2, [{"name": "Apple", "food_ref": ref2, "portion": two}])
    assert r.status_code == 422 and r.json()["error"]["code"] == "invalid_portion"


@pytest.mark.parametrize(
    "portion",
    [
        {"kind": "weight", "amount": 1, "unit": "cup"},
        {"kind": "weight", "amount": -5, "unit": "g"},
        {"kind": "weight", "amount": 0, "unit": "g"},
        {"kind": "weight", "amount": 9000, "unit": "g"},
        {"kind": "range", "min_amount": 200, "max_amount": 100, "unit": "g"},
        {"kind": "range", "min_amount": 100, "max_amount": 100, "unit": "g"},
        {"kind": "grams", "amount": 5},
        {"amount": 5, "unit": "g"},
    ],
)
def test_calculate_rejects_invalid_portions(make_client: Make, portion: dict[str, Any]) -> None:
    c, tok = ready(make_client)
    r = calc(c, tok, [{"name": "Apple", "portion": portion}])
    assert r.status_code == 422


def test_calculate_rejects_client_supplied_nutrient_values(make_client: Make) -> None:
    c, tok = ready(make_client)
    r = calc(c, tok, [{"name": "Apple", "per_100g": {"energy_kcal": 1}, "portion": weight(100)}])
    assert r.status_code == 422
    r2 = calc(c, tok, [{"name": "Apple", "food_ref": "x.y", "portion": weight(100)}])
    assert r2.status_code == 422 and r2.json()["error"]["code"] == "invalid_reference"


def test_tampered_food_ref_is_rejected(make_client: Make) -> None:
    c, tok = ready(make_client)
    ref = search_food(c, tok)[0]["food_ref"]
    body, _, sig = ref.rpartition(".")
    forged = body[:-4] + ("AAAA" if not body.endswith("AAAA") else "BBBB") + "." + sig
    r = calc(c, tok, [{"name": "Apple", "food_ref": forged, "portion": weight(100)}])
    assert r.status_code == 422 and r.json()["error"]["code"] == "invalid_reference"


def test_food_ref_from_another_user_is_rejected(make_client: Make) -> None:
    c, alice = ready(make_client)
    bob = register_user(c, "bob@example.com")
    ref = search_food(c, alice)[0]["food_ref"]
    r = calc(c, bob, [{"name": "Apple", "food_ref": ref, "portion": weight(100)}])
    assert r.status_code == 422 and r.json()["error"]["code"] == "invalid_reference"


def test_expired_food_ref_is_rejected(make_client: Make, monkeypatch: pytest.MonkeyPatch) -> None:
    import time

    import app.core.signed_refs as signed_refs

    c, tok = ready(make_client, settings={"signed_ref_ttl_minutes": 5})
    ref = search_food(c, tok)[0]["food_ref"]
    later = time.time() + 3600
    monkeypatch.setattr(signed_refs, "time", type("T", (), {"time": staticmethod(lambda: later)}))
    r = calc(c, tok, [{"name": "Apple", "food_ref": ref, "portion": weight(100)}])
    assert r.status_code == 422 and r.json()["error"]["code"] == "invalid_reference"


def test_scan_ref_from_another_user_is_rejected_and_origin_tracked(make_client: Make) -> None:
    c, alice = ready(make_client, vision=FakeVision([DetectedFood(name="Apple")]))
    bob = register_user(c, "bob@example.com")
    scan = c.post(
        "/api/v1/food/scan", headers=auth_headers(alice), json={"media_id": upload_photo(c, alice)}
    ).json()
    item = {"name": "Apple", "observed_id": 0, "portion": weight(100)}
    stolen = calc(c, bob, [item], scan_ref=scan["scan_ref"])
    assert stolen.status_code == 422 and stolen.json()["error"]["code"] == "invalid_reference"
    ok = calc(
        c,
        alice,
        [item, {**item, "name": "Green apple", "observed_id": 0}],
        scan_ref=scan["scan_ref"],
    )
    assert ok.status_code == 200
    origins = [i["origin"] for i in ok.json()["items"]]
    assert origins == ["model", "model_edited"]
    assert (
        calc(c, alice, [{**item, "observed_id": 5}], scan_ref=scan["scan_ref"]).status_code == 422
    )
    assert calc(c, alice, [item]).status_code == 422  # observed item without a scan
    user_added = calc(c, alice, [{"name": "Chai", "portion": weight(100)}]).json()
    assert user_added["items"][0]["origin"] == "user_added"


def test_calculate_validation_limits(make_client: Make) -> None:
    c, tok = ready(make_client)
    assert calc(c, tok, []).status_code == 422
    assert calc(c, tok, [{"name": "   "}]).status_code == 422
    assert calc(c, tok, [{"name": "x" * 81}]).status_code == 422
    assert calc(c, tok, [{"name": f"f{i}"} for i in range(31)]).status_code == 422
    assert (
        c.post(
            "/api/v1/food/calculate",
            headers={"Authorization": f"Bearer {tok}"},
            json={"items": [{"name": "a"}]},
        ).status_code
        == 403
    )
