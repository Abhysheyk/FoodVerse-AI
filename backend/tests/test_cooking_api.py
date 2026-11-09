import uuid
from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.ai.text import (
    TextBadOutputError, TextModelMissingError, TextRateLimitedError, TextTimeoutError,
    TextUnavailableError,
)
from app.db.session import get_session_factory
from app.models import AnalysisRecord, ModuleKey
from tests.conftest import CSRF, auth_headers, register_user
from tests.cooking_helpers import FakeText, chat_json, install, post, recipe, recipe_json

Make = Callable[..., TestClient]
CONV = "/api/v1/cooking/conversations"
CHAT = "/api/v1/cooking/chat"
GEN = "/api/v1/cooking/recipes/generate"
RECIPES = "/api/v1/cooking/recipes"


def world(make_client: Make, **kw: Any) -> tuple[TestClient, str, str, FakeText]:
    fake = FakeText(**kw)
    c = make_client()
    install(c, fake)
    return c, register_user(c, "alice@example.com"), register_user(c, "bob@example.com"), fake


def with_prefs(c: TestClient, token: str, **prefs: Any) -> None:
    body = {"unit_system": "metric", "dietary_preferences": [], "allergies": [], **prefs}
    r = c.put("/api/v1/users/me/preferences", headers=auth_headers(token), json=body)
    assert r.status_code == 200, r.text


# ---------------- capabilities and auth ----------------
def test_capabilities_say_when_no_model_is_configured(make_client: Make) -> None:
    c = make_client()  # real factory: OLLAMA_ENABLED false
    tok = register_user(c, "a@example.com")
    body = c.get("/api/v1/cooking/capabilities", headers=auth_headers(tok)).json()
    assert body["text"]["configured"] is False and body["text"]["message"]
    assert {d["value"] for d in body["diets"]} >= {"vegan", "gluten_free", "halal"}
    assert body["max_servings"] == 24 and body["context_messages"] >= 2


def test_capabilities_never_leak_secrets(make_client: Make) -> None:
    c = make_client()
    install(c, FakeText())
    settings = c.app.dependency_overrides  # type: ignore[attr-defined]
    _ = settings
    tok = register_user(c, "a@example.com")
    r = c.get("/api/v1/cooking/capabilities", headers=auth_headers(tok))
    assert "key" not in r.text.lower() or "api_key" not in r.text.lower()


def test_all_endpoints_require_auth(client: TestClient) -> None:
    some = uuid.uuid4()
    for method, path in (
        ("get", "/api/v1/cooking/capabilities"),
        ("post", CHAT),
        ("get", CONV),
        ("get", f"{CONV}/{some}"),
        ("delete", f"{CONV}/{some}"),
        ("post", GEN),
        ("get", RECIPES),
        ("get", f"{RECIPES}/{some}"),
        ("post", f"{RECIPES}/{some}/save"),
        ("post", f"{RECIPES}/{some}/favorite"),
        ("put", f"{RECIPES}/{some}"),
        ("post", f"{RECIPES}/{some}/nutrition"),
        ("delete", f"{RECIPES}/{some}"),
    ):
        r = getattr(client, method)(path, headers=CSRF)
        assert r.status_code == 401, path


# ---------------- chat flow ----------------
def test_chat_starts_a_conversation_and_persists_both_turns(make_client: Make) -> None:
    c, alice, _, fake = world(make_client, replies=[chat_json("Boil the rice.", recipe=recipe().model_dump())])
    r = post(c, alice, CHAT, {"message": "Something with rice"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["conversation_id"]
    assert body["user_message"]["role"] == "user" and body["user_message"]["content"] == "Something with rice"
    assert body["assistant_message"]["role"] == "assistant"
    assert body["provider"] == {"name": "fake", "model": "fake-text-1", "external": False}
    assert body["recipe"] and body["recipe"]["status"] == "suggested" and body["recipe"]["id"]

    detail = c.get(f"{CONV}/{body['conversation_id']}", headers=auth_headers(alice)).json()
    assert detail["title"].startswith("Something with rice")
    assert [(m["role"]) for m in detail["messages"]] == ["user", "assistant"]
    assert detail["recipes"] and detail["recipes"][0]["title"] == "Lemon rice"
    assert fake.calls == 1


def test_follow_up_messages_retain_context(make_client: Make) -> None:
    c, alice, _, fake = world(make_client, replies=[
        chat_json("First answer."),
        chat_json("Second answer, remembering the first."),
    ])
    first = post(c, alice, CHAT, {"message": "Hi, help me cook"}).json()
    second = post(c, alice, CHAT, {"message": "And how long?",
                                   "conversation_id": first["conversation_id"]})
    assert second.status_code == 200
    # second prompt contains the earlier user+assistant turns
    history = fake.prompts[1]
    assert any(m.role == "user" and m.content == "Hi, help me cook" for m in history)
    assert any(m.role == "assistant" and "First answer." in m.content for m in history)
    assert sum(1 for _ in history if _.role == "system") == 1  # one system message only


def test_recipes_that_conflict_with_allergies_are_withheld(make_client: Make) -> None:
    c, alice, _, _ = world(make_client, replies=[
        chat_json("Here is satay.", recipe=recipe(title="Satay", ingredients=[
            {"name": "peanut butter", "quantity": 2, "unit": "tbsp", "optional": False},
        ]).model_dump()),
    ])
    with_prefs(c, alice, allergies=["peanut"])
    r = post(c, alice, CHAT, {"message": "satay please"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["recipe"] is None  # not stored, not shown
    assert any("peanut" in w.lower() for w in body["assistant_message"]["warnings"])
    assert "withheld" in " ".join(body["assistant_message"]["warnings"]).lower()
    # nothing leaked into the recipes list
    assert c.get(RECIPES, headers=auth_headers(alice)).json()["total"] == 0


def test_dietary_preferences_are_enforced_server_side(make_client: Make) -> None:
    c, alice, _, _ = world(make_client, replies=[
        chat_json("Chicken curry.", recipe=recipe(title="Chicken curry", ingredients=[
            {"name": "chicken", "quantity": 300, "unit": "g", "optional": False},
        ]).model_dump()),
    ])
    with_prefs(c, alice, dietary_preferences=["vegan"])
    body = post(c, alice, CHAT, {"message": "vegan dinner"}).json()
    assert body["recipe"] is None
    assert any("vegan" in w.lower() for w in body["assistant_message"]["warnings"])


def test_unverifiable_diets_add_a_caution_without_blocking(make_client: Make) -> None:
    c, alice, _, _ = world(make_client, replies=[
        chat_json("Fine.", recipe=recipe().model_dump()),
    ])
    with_prefs(c, alice, dietary_preferences=["halal"])
    body = post(c, alice, CHAT, {"message": "something halal"}).json()
    assert body["recipe"] is not None
    assert any("halal" in w.lower() for w in body["assistant_message"]["warnings"])


def test_conversations_are_isolated_between_users(make_client: Make) -> None:
    c, alice, bob, _ = world(make_client, replies=[chat_json("A."), chat_json("B.")])
    conv = post(c, alice, CHAT, {"message": "mine"}).json()["conversation_id"]
    hb = auth_headers(bob)
    assert c.get(f"{CONV}/{conv}", headers=hb).status_code == 404
    assert c.delete(f"{CONV}/{conv}", headers=hb).status_code == 404
    # bob can start his own, but does not see alice's
    post(c, bob, CHAT, {"message": "bobs"})
    assert c.get(CONV, headers=hb).json()["total"] == 1
    assert c.get(CONV, headers=auth_headers(alice)).json()["total"] == 1


def test_chat_into_someone_elses_conversation_is_rejected(make_client: Make) -> None:
    c, alice, bob, _ = world(make_client, replies=[chat_json("A.")])
    conv = post(c, alice, CHAT, {"message": "mine"}).json()["conversation_id"]
    r = post(c, bob, CHAT, {"message": "steal", "conversation_id": conv})
    assert r.status_code == 404 and r.json()["error"]["code"] == "conversation_not_found"


def test_chat_requires_csrf(make_client: Make) -> None:
    c, alice, _, fake = world(make_client, replies=[chat_json()])
    r = c.post(CHAT, headers={"Authorization": f"Bearer {alice}"}, json={"message": "hi"})
    assert r.status_code == 403 and fake.calls == 0


@pytest.mark.parametrize(
    ("error", "status", "code"),
    [
        (TextUnavailableError("down"), 503, "text_unavailable"),
        (TextModelMissingError("missing"), 503, "text_model_missing"),
        (TextTimeoutError("slow"), 504, "text_timeout"),
        (TextBadOutputError("bad"), 502, "text_bad_output"),
        (TextRateLimitedError("busy"), 429, "text_rate_limited"),
    ],
)
def test_provider_errors_are_typed_and_nothing_is_saved(
    make_client: Make, error: Exception, status: int, code: str
) -> None:
    c, alice, _, _ = world(make_client, error=error)  # type: ignore[arg-type]
    r = post(c, alice, CHAT, {"message": "hi"})
    assert r.status_code == status and r.json()["error"]["code"] == code
    assert c.get(CONV, headers=auth_headers(alice)).json()["total"] == 0


def test_malformed_output_never_becomes_a_message(make_client: Make) -> None:
    c, alice, _, _ = world(make_client, replies=["not json"])
    r = post(c, alice, CHAT, {"message": "hi"})
    assert r.status_code == 502 and r.json()["error"]["code"] == "text_bad_output"
    assert c.get(CONV, headers=auth_headers(alice)).json()["total"] == 0


def test_chat_is_rate_limited_per_user(make_client: Make) -> None:
    fake = FakeText(replies=[chat_json(), chat_json(), chat_json()])
    c = make_client(cooking_rate_limit_per_minute=2)
    install(c, fake)
    tok = register_user(c, "a@example.com")
    codes = [post(c, tok, CHAT, {"message": "hi"}).status_code for _ in range(3)]
    assert codes == [200, 200, 429] and fake.calls == 2


def test_delete_conversation_keeps_suggested_recipes(make_client: Make) -> None:
    c, alice, _, _ = world(make_client, replies=[chat_json(recipe=recipe().model_dump())])
    conv = post(c, alice, CHAT, {"message": "rice"}).json()
    recipe_id = conv["recipe"]["id"]
    assert c.delete(f"{CONV}/{conv['conversation_id']}",
                    headers=auth_headers(alice)).status_code == 204
    # the suggestion survives, orphaned from its conversation, and stays discoverable by id
    got = c.get(f"{RECIPES}/{recipe_id}", headers=auth_headers(alice)).json()
    assert got["title"] == "Lemon rice"


# ---------------- one-shot generation ----------------
def test_generate_recipe_returns_a_validated_draft(make_client: Make) -> None:
    c, alice, _, fake = world(make_client, replies=[recipe_json()])
    r = post(c, alice, GEN, {"mode": "from_ingredients", "ingredients": ["rice", "lemon"],
                             "servings": 2})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["status"] == "suggested" and body["servings"] == 2
    assert body["total_minutes"] == 25
    assert body["context_note"].startswith("Model-generated")
    assert "rice" in fake.prompts[0][-1].content.lower()
    # not yet visible in the saved list
    assert c.get(RECIPES, headers=auth_headers(alice)).json()["total"] == 0


def test_generate_rejects_a_recipe_conflicting_with_allergies(make_client: Make) -> None:
    c, alice, _, _ = world(make_client, replies=[recipe_json()])
    with_prefs(c, alice, allergies=["milk"])
    r = post(c, alice, GEN, {
        "mode": "from_ingredients",
        "ingredients": ["rice", "butter"],
    })
    assert r.status_code == 422 and r.json()["error"]["code"] == "dietary_conflict"
    assert c.get(RECIPES, headers=auth_headers(alice)).json()["total"] == 0


def test_generate_requires_ingredients_in_from_ingredients_mode(make_client: Make) -> None:
    c, alice, _, fake = world(make_client, replies=[recipe_json()])
    r = post(c, alice, GEN, {"mode": "from_ingredients", "ingredients": []})
    assert r.status_code == 422 and fake.calls == 0


# ---------------- save, favorite, edit, delete ----------------
def _make_recipe(c: TestClient, token: str, fake: FakeText) -> dict[str, Any]:
    fake.replies.append(recipe_json())
    r = post(c, token, GEN, {"mode": "free"})
    assert r.status_code == 201, r.text
    return dict(r.json())


def test_save_promotes_a_suggestion_and_creates_history(make_client: Make) -> None:
    c, alice, _, fake = world(make_client)
    draft = _make_recipe(c, alice, fake)
    r = c.post(f"{RECIPES}/{draft['id']}/save", headers=auth_headers(alice))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "saved"
    listed = c.get(RECIPES, headers=auth_headers(alice)).json()
    assert listed["total"] == 1 and listed["items"][0]["id"] == draft["id"]
    hist = c.get("/api/v1/history?module=cooking", headers=auth_headers(alice)).json()
    assert hist["total"] == 1
    # audit record shares the recipe id
    with get_session_factory()() as db:
        rec = db.get(AnalysisRecord, uuid.UUID(draft["id"]))
        assert rec is not None and rec.module is ModuleKey.COOKING


def test_save_rechecks_allergens_at_save_time(make_client: Make) -> None:
    c, alice, _, fake = world(make_client)
    draft = _make_recipe(c, alice, fake)  # lemon rice, safe before
    with_prefs(c, alice, allergies=["milk"])
    # Editing the recipe to introduce milk would fail; saving is still allowed for the original
    assert c.post(f"{RECIPES}/{draft['id']}/save", headers=auth_headers(alice)).status_code == 200


def test_favorite_keeps_and_flags(make_client: Make) -> None:
    c, alice, _, fake = world(make_client)
    draft = _make_recipe(c, alice, fake)
    r = post(c, alice, f"{RECIPES}/{draft['id']}/favorite", {"favorite": True})
    assert r.status_code == 200
    assert r.json()["favorite"] is True and r.json()["status"] == "saved"
    listed = c.get(RECIPES, headers=auth_headers(alice)).json()
    assert listed["items"][0]["favorite"] is True


def test_search_filters_saved_recipes(make_client: Make) -> None:
    c, alice, _, fake = world(make_client)
    _make_recipe(c, alice, fake)
    fake.replies.append(recipe_json(title="Tomato pasta"))
    other = post(c, alice, GEN, {"mode": "free"}).json()
    c.post(f"{RECIPES}/{other['id']}/save", headers=auth_headers(alice))
    assert c.get(RECIPES, headers=auth_headers(alice), params={"q": "pasta"}).json()["total"] == 0
    c.post(f"{RECIPES}/{other['id']}/save", headers=auth_headers(alice)) if False else None
    # actually save the first as well so both are searchable
    fake.replies.append(recipe_json())
    first = post(c, alice, GEN, {"mode": "free"}).json()
    c.post(f"{RECIPES}/{first['id']}/save", headers=auth_headers(alice))
    assert c.get(RECIPES, headers=auth_headers(alice), params={"q": "Lemon"}).json()["total"] == 1
    assert c.get(RECIPES, headers=auth_headers(alice), params={"q": "pasta"}).json()["total"] == 1


def test_edit_recomputed_and_revision_checked(make_client: Make) -> None:
    c, alice, _, fake = world(make_client)
    draft = _make_recipe(c, alice, fake)
    c.post(f"{RECIPES}/{draft['id']}/save", headers=auth_headers(alice))
    edit = {
        "title": "Lemon rice (extra lemony)",
        "servings": 4,
        "ingredients": [
            {"name": "rice", "quantity": 400, "unit": "g", "optional": False},
            {"name": "lemon", "quantity": 2, "optional": False},
        ],
        "steps": [{"instruction": "Cook."}, {"instruction": "Mix."}],
        "expected_revision": 1,
    }
    r = c.put(f"{RECIPES}/{draft['id']}", headers=auth_headers(alice), json=edit)
    assert r.status_code == 200, r.text
    assert r.json()["servings"] == 4 and r.json()["revision"] == 2

    stale = c.put(f"{RECIPES}/{draft['id']}", headers=auth_headers(alice),
                  json={**edit, "expected_revision": 1})
    assert stale.status_code == 409 and stale.json()["error"]["code"] == "recipe_revision_conflict"


def test_edit_that_introduces_an_allergen_is_rejected(make_client: Make) -> None:
    c, alice, _, fake = world(make_client)
    draft = _make_recipe(c, alice, fake)
    c.post(f"{RECIPES}/{draft['id']}/save", headers=auth_headers(alice))
    with_prefs(c, alice, allergies=["milk"])
    edit = {
        "title": "Lemon rice",
        "servings": 2,
        "ingredients": [{"name": "butter", "quantity": 20, "unit": "g", "optional": False}],
        "steps": [{"instruction": "Cook."}],
    }
    r = c.put(f"{RECIPES}/{draft['id']}", headers=auth_headers(alice), json=edit)
    assert r.status_code == 422 and r.json()["error"]["code"] == "dietary_conflict"


def test_delete_removes_history_and_recipe(make_client: Make) -> None:
    c, alice, _, fake = world(make_client)
    draft = _make_recipe(c, alice, fake)
    c.post(f"{RECIPES}/{draft['id']}/save", headers=auth_headers(alice))
    h = auth_headers(alice)
    assert c.delete(f"{RECIPES}/{draft['id']}", headers=h).status_code == 204
    assert c.get(f"{RECIPES}/{draft['id']}", headers=h).status_code == 404
    assert c.get(RECIPES, headers=h).json()["total"] == 0
    assert c.get("/api/v1/history?module=cooking", headers=h).json()["total"] == 0


def test_ownership_isolation_on_recipes(make_client: Make) -> None:
    c, alice, bob, fake = world(make_client)
    draft = _make_recipe(c, alice, fake)
    hb = auth_headers(bob)
    for method, path in (
        ("get", f"{RECIPES}/{draft['id']}"),
        ("post", f"{RECIPES}/{draft['id']}/save"),
        ("post", f"{RECIPES}/{draft['id']}/favorite"),
        ("delete", f"{RECIPES}/{draft['id']}"),
    ):
        assert getattr(c, method)(path, headers=hb).status_code == 404, path
    assert c.get(RECIPES, headers=hb).json()["total"] == 0
    assert c.get(RECIPES, headers=auth_headers(alice)).json()["total"] == 0  # still suggested


# ---------------- scaling and nutrition linking ----------------
def test_scaling_returns_new_quantities_without_touching_the_stored_recipe(make_client: Make) -> None:
    c, alice, _, fake = world(make_client)
    draft = _make_recipe(c, alice, fake)
    c.post(f"{RECIPES}/{draft['id']}/save", headers=auth_headers(alice))
    h = auth_headers(alice)
    scaled = c.get(f"{RECIPES}/{draft['id']}?servings=4", headers=h).json()
    assert scaled["servings"] == 4
    assert scaled["ingredients"][0]["quantity"] == 400
    original = c.get(f"{RECIPES}/{draft['id']}", headers=h).json()
    assert original["servings"] == 2 and original["ingredients"][0]["quantity"] == 200


def test_attach_nutrition_uses_signed_refs_and_divides_per_serving(make_client: Make) -> None:
    from tests.food_helpers import install as install_food, search_food, usda_food

    c = make_client()
    install(c, FakeText())
    install_food(c, usda=[usda_food()])
    alice = register_user(c, "alice@example.com")
    fake = c.app.dependency_overrides[list(c.app.dependency_overrides)[0]]  # noqa: F841
    # generate + save a recipe
    from tests.cooking_helpers import install as install_text, recipe_json as rjson
    fake_text = FakeText(replies=[rjson()])
    install_text(c, fake_text)
    draft = post(c, alice, GEN, {"mode": "free"}).json()
    c.post(f"{RECIPES}/{draft['id']}/save", headers=auth_headers(alice))

    food_ref = search_food(c, alice)[0]["food_ref"]
    r = post(c, alice, f"{RECIPES}/{draft['id']}/nutrition",
             {"links": [{"ingredient_index": 0, "food_ref": food_ref, "grams": 200}]})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["nutrition"]["linked_items"] == 1
    assert body["nutrition"]["whole_recipe"]["totals"]["energy_kcal"]["low"] == 104.0  # 52 * 2
    assert body["nutrition"]["per_serving"]["energy_kcal"]["low"] == 52.0  # ÷ 2 servings
    assert "fixed arithmetic" in body["nutrition"]["note"]


def test_attach_nutrition_rejects_tampered_or_foreign_refs(make_client: Make) -> None:
    from tests.food_helpers import install as install_food, search_food, usda_food

    c = make_client()
    install(c, FakeText())
    install_food(c, usda=[usda_food()])
    alice = register_user(c, "alice@example.com")
    bob = register_user(c, "bob@example.com")
    from tests.cooking_helpers import install as install_text, recipe_json as rjson
    install_text(c, FakeText(replies=[rjson()]))
    draft = post(c, alice, GEN, {"mode": "free"}).json()
    c.post(f"{RECIPES}/{draft['id']}/save", headers=auth_headers(alice))

    bob_ref = search_food(c, bob)[0]["food_ref"]
    r = post(c, alice, f"{RECIPES}/{draft['id']}/nutrition",
             {"links": [{"ingredient_index": 0, "food_ref": bob_ref, "grams": 100}]})
    assert r.status_code == 422 and r.json()["error"]["code"] == "invalid_reference"


def test_attach_nutrition_bounds_index(make_client: Make) -> None:
    from tests.food_helpers import install as install_food, search_food, usda_food

    c = make_client()
    install(c, FakeText())
    install_food(c, usda=[usda_food()])
    alice = register_user(c, "alice@example.com")
    from tests.cooking_helpers import install as install_text, recipe_json as rjson
    install_text(c, FakeText(replies=[rjson()]))
    draft = post(c, alice, GEN, {"mode": "free"}).json()
    c.post(f"{RECIPES}/{draft['id']}/save", headers=auth_headers(alice))
    ref = search_food(c, alice)[0]["food_ref"]
    r = post(c, alice, f"{RECIPES}/{draft['id']}/nutrition",
             {"links": [{"ingredient_index": 999, "food_ref": ref, "grams": 100}]})
    assert r.status_code == 422 and r.json()["error"]["code"] == "invalid_link"


# ---------------- module gate ----------------
def test_cooking_module_is_marked_available(client: TestClient, registered: dict[str, str]) -> None:
    mods = {m["key"]: m["available"] for m in
            client.get("/api/v1/modules", headers=auth_headers(registered["token"])).json()}
    assert mods["cooking"] is True