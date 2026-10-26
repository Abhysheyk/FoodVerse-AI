"""USDA FoodData Central (generic composition data).

Only the Foundation and SR Legacy data types are requested: their nutrient values are published
per 100 g of the food, which is the basis the calculator relies on. Branded foods are left to
Open Food Facts. The API key stays on the server and is sent only to the configured base URL.

The parser accepts both nutrient shapes FDC uses (search results: nutrientNumber/unitName/value;
food details: nutrient{number,unitName}/amount) and rejects anything out of range.
"""

import math
from typing import Any

import httpx

from app.nutrition.nutrients import NUTRIENT_BY_KEY
from app.nutrition.sources.base import NutritionSource
from app.nutrition.types import FoodCandidate, NutritionSourceError

# nutrient number -> (our key, expected unit)
_NUMBER_MAP: dict[str, tuple[str, str]] = {
    "208": ("energy_kcal", "kcal"),
    "203": ("protein_g", "g"),
    "205": ("carbs_g", "g"),
    "204": ("fat_g", "g"),
    "291": ("fiber_g", "g"),
    "269": ("sugars_g", "g"),
    "269.3": ("sugars_g", "g"),
    "606": ("saturated_fat_g", "g"),
    "307": ("sodium_mg", "mg"),
}
# Energy fallbacks (Atwater factors, kcal) used by many Foundation foods that lack nutrient 208.
_ENERGY_FALLBACK = ("958", "957")
_DATA_TYPES = "Foundation,SR Legacy"
ATTRIBUTION = "USDA FoodData Central (U.S. Department of Agriculture), https://fdc.nal.usda.gov"


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float | str):
        return None
    try:
        number = float(value)
    except ValueError:
        return None
    return number if math.isfinite(number) and number >= 0 else None


def _nutrient_fields(entry: dict[str, Any]) -> tuple[str | None, str | None, float | None]:
    raw_nested = entry.get("nutrient")
    nested: dict[str, Any] = raw_nested if isinstance(raw_nested, dict) else {}
    number = entry.get("nutrientNumber") or nested.get("number")
    unit = entry.get("unitName") or nested.get("unitName")
    value = entry.get("value") if entry.get("value") is not None else entry.get("amount")
    return (
        str(number).strip() if number is not None else None,
        str(unit).strip().lower() if unit is not None else None,
        _number(value),
    )


def parse_food(food: dict[str, Any]) -> FoodCandidate | None:
    name = str(food.get("description") or "").strip()
    fdc_id = food.get("fdcId")
    entries = food.get("foodNutrients")
    if not name or fdc_id is None or not isinstance(entries, list):
        return None

    values: dict[str, float] = {}
    energy_fallback: dict[str, float] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        number, unit, value = _nutrient_fields(entry)
        if number is None or value is None:
            continue
        if number in _ENERGY_FALLBACK and unit == "kcal":
            energy_fallback[number] = value
            continue
        mapped = _NUMBER_MAP.get(number)
        if mapped is None or unit != mapped[1]:
            continue  # unknown nutrient, or an unexpected unit: treat as not reported
        key = mapped[0]
        if value > NUTRIENT_BY_KEY[key].max_per_100g:
            continue  # implausible per-100 g value: malformed, not reported
        values.setdefault(key, value)
    notes: list[str] = []
    if "energy_kcal" not in values:
        for number in _ENERGY_FALLBACK:
            if number in energy_fallback and energy_fallback[number] <= 1000.0:
                values["energy_kcal"] = energy_fallback[number]
                notes.append("Calories from the source's Atwater energy value.")
                break
    if not values:
        return None
    data_type = str(food.get("dataType") or "").strip() or None
    return FoodCandidate(
        source="usda_fdc",
        source_label="USDA FoodData Central",
        source_id=str(fdc_id),
        name=name,
        brand=None,
        data_type=data_type,
        per_100g=values,
        attribution=ATTRIBUTION,
        url=f"https://fdc.nal.usda.gov/fdc-app.html#/food-details/{fdc_id}/nutrients",
        notes=notes,
    )


class UsdaFdcSource:
    name = "usda_fdc"
    label = "USDA FoodData Central"

    def __init__(
        self,
        api_key: str,
        base_url: str,
        timeout_seconds: float,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_seconds
        self._transport = transport

    def search(self, query: str, limit: int) -> list[FoodCandidate]:
        params = {
            "api_key": self._api_key,
            "query": query,
            "pageSize": str(limit),
            "dataType": _DATA_TYPES,
        }
        try:
            with httpx.Client(timeout=self._timeout, transport=self._transport) as client:
                response = client.get(f"{self._base_url}/foods/search", params=params)
        except httpx.TimeoutException:
            raise NutritionSourceError("timeout", "USDA FoodData Central timed out.") from None
        except httpx.HTTPError:
            raise NutritionSourceError(
                "unavailable", "USDA FoodData Central is unreachable."
            ) from None

        if response.status_code == 429:
            raise NutritionSourceError(
                "rate_limited", "USDA FoodData Central is rate limiting this server's key."
            )
        if response.status_code in (400, 401, 403):
            raise NutritionSourceError(
                "unavailable", "USDA FoodData Central rejected the request or the configured key."
            )
        if response.status_code >= 400:
            raise NutritionSourceError(
                "unavailable",
                f"USDA FoodData Central returned an error (HTTP {response.status_code}).",
            )
        try:
            foods = response.json()["foods"]
            if not isinstance(foods, list):
                raise TypeError
        except (ValueError, KeyError, TypeError):
            raise NutritionSourceError(
                "unavailable", "USDA FoodData Central returned an unexpected response."
            ) from None
        results = [c for f in foods if isinstance(f, dict) and (c := parse_food(f)) is not None]
        return results[:limit]


_check: type[NutritionSource] = UsdaFdcSource  # structural check against the Protocol
