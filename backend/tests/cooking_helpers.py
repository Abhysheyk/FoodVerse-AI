"""Fakes for the cooking workflow. No test here touches a network or a real model."""

import json
from typing import Any

from fastapi.testclient import TestClient

from app.ai.cooking import RecipeDraft
from app.ai.text import ChatTurn, TextProviderInfo
from app.api.deps import get_text_factory
from tests.conftest import auth_headers


class FakeText:
    def __init__(self, replies: list[str] | None = None, error: Exception | None = None) -> None:
        self.replies = list(replies or [])
        self.error = error
        self.calls = 0
        self.prompts: list[list[ChatTurn]] = []
        self.info = TextProviderInfo(name="fake", model="fake-text-1", external=False)

    def complete(self, messages: list[ChatTurn], schema: dict[str, Any] | None = None) -> str:
        self.calls += 1
        self.prompts.append(messages)
        if self.error:
            raise self.error
        return self.replies.pop(0) if self.replies else "{}"


def install(client: TestClient, text: FakeText) -> None:
    overrides = client.app.dependency_overrides  # type: ignore[attr-defined]
    overrides[get_text_factory] = lambda: (lambda: text)


def recipe(**over: Any) -> RecipeDraft:
    base: dict[str, Any] = {
        "title": "Lemon rice",
        "description": "A quick one-pot rice.",
        "servings": 2,
        "prep_minutes": 10,
        "cook_minutes": 15,
        "equipment": ["pan"],
        "ingredients": [
            {"name": "rice", "quantity": 200, "unit": "g", "optional": False},
            {"name": "lemon", "quantity": 1, "unit": None, "optional": False},
            {"name": "salt", "quantity": None, "unit": None, "note": "to taste", "optional": False},
        ],
        "steps": [{"instruction": "Cook the rice."}, {"instruction": "Fold in the lemon."}],
        "substitutions": [{"ingredient": "lemon", "alternative": "lime"}],
        "dietary_tags": ["vegetarian"],
        "allergen_warnings": [],
        "safety_notes": ["Cool leftovers quickly."],
        "beginner_notes": ["Rinse the rice first."],
        "tips": ["Add peanuts for crunch."],
    }
    base.update(over)
    return RecipeDraft.model_validate(base)


def recipe_json(**over: Any) -> str:
    return json.dumps(recipe(**over).model_dump(mode="json"))


def chat_json(reply: str = "Here is a recipe.", **over: Any) -> str:
    payload: dict[str, Any] = {"reply": reply, "follow_up_questions": ["Want it spicier?"]}
    payload.update(over)
    return json.dumps(payload)


def post(client: TestClient, token: str, path: str, body: dict[str, Any]) -> Any:
    return client.post(path, headers=auth_headers(token), json=body)