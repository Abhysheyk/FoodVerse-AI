"""Fakes for the food workflow. No test here touches the network or a real model: vision output
and nutrition-source HTTP responses are scripted, and the *real* parsing, signing, calculation
and persistence code runs on top of them."""

import uuid
from collections.abc import Callable
from typing import Any

import httpx
from fastapi import Depends
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy.orm import Session

from app.ai.vision import (
    DetectedFood,
    VisionError,
    VisionProviderInfo,
    VisionResult,
)
from app.api.deps import get_nutrition_service, get_vision_factory
from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.nutrition.service import NutritionService, build_nutrition_service
from tests.conftest import auth_headers
from tests.imgs import make_image


class FakeVision:
    """Scripted vision provider: returns a fixed result or raises a fixed error."""

    def __init__(
        self,
        items: list[DetectedFood] | None = None,
        error: VisionError | None = None,
        raw: str | None = None,
    ) -> None:
        self.items = items if items is not None else []
        self.error = error
        self.raw = raw  # scripted reply for complete_json (e.g. a freshness JSON document)
        self.calls = 0
        self.images: list[bytes] = []
        self.prompts: list[str] = []
        self.info = VisionProviderInfo(name="fake", model="fake-vision-1", external=False)

    def identify(self, image: bytes) -> VisionResult:
        self.calls += 1
        self.images.append(image)
        if self.error:
            raise self.error
        return VisionResult(items=self.items, notes="scripted")

    def complete_json(self, image: bytes, prompt: str, schema: dict[str, Any]) -> str:
        self.calls += 1
        self.images.append(image)
        self.prompts.append(prompt)
        if self.error:
            raise self.error
        return self.raw if self.raw is not None else ""


def usda_food(
    fdc_id: int = 171688,
    name: str = "Apples, raw, with skin",
    nutrients: dict[str, float] | None = None,
) -> dict[str, Any]:
    values = (
        nutrients
        if nutrients is not None
        else {"208": 52.0, "203": 0.26, "205": 13.8, "204": 0.17, "291": 2.4, "269": 10.4}
    )
    units = {"208": "KCAL", "307": "MG"}
    return {
        "fdcId": fdc_id,
        "description": name,
        "dataType": "SR Legacy",
        "foodNutrients": [
            {"nutrientNumber": n, "unitName": units.get(n, "G"), "value": v}
            for n, v in values.items()
        ],
    }


def off_product(code: str = "5000112637922", name: str = "Oat Biscuit") -> dict[str, Any]:
    return {
        "code": code,
        "product_name": name,
        "brands": "Acme",
        "serving_size": "30 g",
        "nutriments": {
            "energy-kcal_100g": 450,
            "proteins_100g": 7,
            "carbohydrates_100g": 65,
            "fat_100g": 18,
            "sodium_100g": 0.4,
        },
    }


Handler = Callable[[httpx.Request], httpx.Response]


def source_router(
    usda: Handler | list[dict[str, Any]] | None = None,
    off: Handler | list[dict[str, Any]] | None = None,
) -> Handler:
    def respond(
        spec: Handler | list[dict[str, Any]] | None, key: str, req: httpx.Request
    ) -> httpx.Response:
        if spec is None:
            return httpx.Response(500)
        if callable(spec):
            return spec(req)
        return httpx.Response(200, json={key: spec})

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/foods/search"):
            return respond(usda, "foods", request)
        if "search.pl" in request.url.path:
            return respond(off, "products", request)
        if "/api/v2/product/" in request.url.path:
            if callable(off):
                return off(request)
            product = off[0] if off else None
            return httpx.Response(200, json={"product": product, "status": 1 if product else 0})
        return httpx.Response(404)

    return handler


def install(
    client: TestClient,
    *,
    vision: FakeVision | None = None,
    usda: Handler | list[dict[str, Any]] | None = None,
    off: Handler | list[dict[str, Any]] | None = None,
    use_usda: bool = True,
    use_off: bool = False,
) -> Settings:
    """Wire fake vision + scripted nutrition HTTP into this client's app."""
    base: Settings = client.app.dependency_overrides.get(get_settings, get_settings)()  # type: ignore[attr-defined]
    settings = base.model_copy(
        update={
            "usda_fdc_api_key": SecretStr("test-usda-key-123") if use_usda else None,
            "open_food_facts_enabled": use_off,
        }
    )
    handler = source_router(usda, off)

    def nutrition(db: Session = Depends(get_db)) -> NutritionService:  # noqa: B008
        return build_nutrition_service(settings, db, httpx.MockTransport(handler))

    overrides = client.app.dependency_overrides  # type: ignore[attr-defined]
    overrides[get_nutrition_service] = nutrition
    if vision is not None:
        overrides[get_vision_factory] = lambda: lambda: vision
    return settings


def upload_photo(client: TestClient, token: str, name: str = "plate.png") -> str:
    r = client.post(
        "/api/v1/media",
        headers=auth_headers(token),
        files={"file": (name, make_image("PNG", (64, 48)), "image/png")},
    )
    assert r.status_code == 201, r.text
    return str(r.json()["id"])


def search_food(client: TestClient, token: str, q: str = "apple") -> list[dict[str, Any]]:
    r = client.get(f"/api/v1/nutrition/search?q={q}", headers=auth_headers(token))
    assert r.status_code == 200, r.text
    return list(r.json()["results"])


def weight(grams: float) -> dict[str, Any]:
    return {"kind": "weight", "amount": grams, "unit": "g"}


def calc(
    client: TestClient, token: str, items: list[dict[str, Any]], **extra: Any
) -> httpx.Response:
    response: httpx.Response = client.post(
        "/api/v1/food/calculate", headers=auth_headers(token), json={"items": items, **extra}
    )
    return response


def new_id() -> str:
    return str(uuid.uuid4())
