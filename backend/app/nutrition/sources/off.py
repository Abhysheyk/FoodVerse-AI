"""Open Food Facts (packaged foods; community-contributed, ODbL licensed).

Values are per 100 g as printed on packages. The data is crowd-sourced, so candidates carry a
caution. No API key is needed, but OFF asks every client to identify itself with a User-Agent,
and rate-limits searches (about 10 per minute per IP), so failures here are expected and surfaced.
Energy is taken from energy-kcal_100g; if only kJ is supplied it is converted (1 kcal = 4.184 kJ)
and the candidate says so. Sodium is reported in grams by OFF and converted to mg.
"""

import math
import re
from typing import Any

import httpx

from app.nutrition.nutrients import NUTRIENT_BY_KEY
from app.nutrition.sources.base import NutritionSource
from app.nutrition.types import FoodCandidate, NutritionSourceError

ATTRIBUTION = (
    "Open Food Facts (ODbL), community-contributed data. Check the product label if it matters."
)
_FIELDS = "code,product_name,brands,nutriments,serving_size"
_GRAMS_PER_100G_KEYS: dict[str, str] = {
    "protein_g": "proteins_100g",
    "carbs_g": "carbohydrates_100g",
    "fat_g": "fat_100g",
    "fiber_g": "fiber_100g",
    "sugars_g": "sugars_100g",
    "saturated_fat_g": "saturated-fat_100g",
}
_SERVING_GRAMS = re.compile(r"(?<![\w.])(\d{1,4}(?:[.,]\d+)?)\s*g\b", re.IGNORECASE)
_BARCODE = re.compile(r"^\d{8,14}$")


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float | str):
        return None
    try:
        number = float(str(value).replace(",", "."))
    except ValueError:
        return None
    return number if math.isfinite(number) and number >= 0 else None


def parse_product(product: dict[str, Any]) -> FoodCandidate | None:
    name = str(product.get("product_name") or "").strip()
    code = str(product.get("code") or "").strip()
    nutriments = product.get("nutriments")
    if not name or not code or not isinstance(nutriments, dict):
        return None

    values: dict[str, float] = {}
    notes: list[str] = []

    kcal = _number(nutriments.get("energy-kcal_100g"))
    if kcal is None:
        kj = _number(nutriments.get("energy-kj_100g"))
        if kj is None:
            kj = _number(nutriments.get("energy_100g"))  # OFF's generic energy key is kJ
        if kj is not None:
            kcal = round(kj / 4.184, 1)
            notes.append("Calories converted from kJ (1 kcal = 4.184 kJ).")
    if kcal is not None and kcal <= NUTRIENT_BY_KEY["energy_kcal"].max_per_100g:
        values["energy_kcal"] = kcal
    elif kcal is not None:
        notes = [n for n in notes if "converted" not in n]

    for key, off_key in _GRAMS_PER_100G_KEYS.items():
        number = _number(nutriments.get(off_key))
        if number is not None and number <= NUTRIENT_BY_KEY[key].max_per_100g:
            values[key] = number
    sodium_g = _number(nutriments.get("sodium_100g"))
    if sodium_g is not None and sodium_g * 1000 <= NUTRIENT_BY_KEY["sodium_mg"].max_per_100g:
        values["sodium_mg"] = round(sodium_g * 1000, 1)
    if not values:
        return None

    serving_label = str(product.get("serving_size") or "").strip() or None
    serving_grams: float | None = None
    if serving_label:
        match = _SERVING_GRAMS.search(serving_label)
        if match:
            grams = _number(match.group(1))
            if grams is not None and 0 < grams <= 2000:
                serving_grams = grams

    brand = str(product.get("brands") or "").split(",")[0].strip() or None
    return FoodCandidate(
        source="open_food_facts",
        source_label="Open Food Facts",
        source_id=code,
        name=name,
        brand=brand,
        data_type="Packaged product (community data)",
        per_100g=values,
        serving_grams=serving_grams,
        serving_label=serving_label,
        attribution=ATTRIBUTION,
        url=f"https://world.openfoodfacts.org/product/{code}",
        notes=notes,
    )


class OpenFoodFactsSource:
    name = "open_food_facts"
    label = "Open Food Facts"

    def __init__(
        self,
        base_url: str,
        user_agent: str,
        timeout_seconds: float,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._headers = {"User-Agent": user_agent}
        self._timeout = timeout_seconds
        self._transport = transport

    def _get(self, path: str, params: dict[str, str]) -> Any:
        try:
            with httpx.Client(
                timeout=self._timeout, transport=self._transport, headers=self._headers
            ) as client:
                response = client.get(f"{self._base_url}{path}", params=params)
        except httpx.TimeoutException:
            raise NutritionSourceError("timeout", "Open Food Facts timed out.") from None
        except httpx.HTTPError:
            raise NutritionSourceError("unavailable", "Open Food Facts is unreachable.") from None
        if response.status_code in (429, 503):
            raise NutritionSourceError(
                "rate_limited", "Open Food Facts is rate limiting requests. Try again shortly."
            )
        if response.status_code >= 400:
            raise NutritionSourceError(
                "unavailable", f"Open Food Facts returned an error (HTTP {response.status_code})."
            )
        try:
            return response.json()
        except ValueError:
            raise NutritionSourceError(
                "unavailable", "Open Food Facts returned an unexpected response."
            ) from None

    def search(self, query: str, limit: int) -> list[FoodCandidate]:
        data = self._get(
            "/cgi/search.pl",
            {
                "search_terms": query,
                "search_simple": "1",
                "action": "process",
                "json": "1",
                "page_size": str(limit),
                "fields": _FIELDS,
            },
        )
        products = data.get("products") if isinstance(data, dict) else None
        if not isinstance(products, list):
            raise NutritionSourceError(
                "unavailable", "Open Food Facts returned an unexpected response."
            )
        results = [c for p in products if isinstance(p, dict) and (c := parse_product(p))]
        return results[:limit]

    def lookup_barcode(self, barcode: str) -> FoodCandidate | None:
        if not _BARCODE.fullmatch(barcode):
            raise ValueError("A barcode is 8 to 14 digits.")
        data = self._get(f"/api/v2/product/{barcode}.json", {"fields": _FIELDS})
        product = data.get("product") if isinstance(data, dict) else None
        return parse_product(product) if isinstance(product, dict) else None


_check: type[NutritionSource] = OpenFoodFactsSource  # structural check against the Protocol
