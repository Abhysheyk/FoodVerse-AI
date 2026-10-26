import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
import pytest

from app.db.session import get_session_factory
from app.nutrition.import_reference import import_csv
from app.nutrition.sources.off import OpenFoodFactsSource, parse_product
from app.nutrition.sources.usda import UsdaFdcSource, parse_food
from app.nutrition.types import NutritionSourceError
from tests.food_helpers import off_product, usda_food


def _usda(handler: Callable[[httpx.Request], httpx.Response]) -> UsdaFdcSource:
    return UsdaFdcSource("secret-key", "https://fdc.test/v1", 5, httpx.MockTransport(handler))


def _off(handler: Callable[[httpx.Request], httpx.Response]) -> OpenFoodFactsSource:
    return OpenFoodFactsSource("https://off.test", "Test/1", 5, httpx.MockTransport(handler))


# ---- USDA ----
def test_usda_parses_per_100g_and_keeps_provenance() -> None:
    c = parse_food(usda_food())
    assert c is not None
    assert c.source == "usda_fdc" and c.source_id == "171688"
    assert c.per_100g["energy_kcal"] == 52.0 and c.per_100g["fiber_g"] == 2.4
    assert "fdc.nal.usda.gov" in c.attribution


def test_usda_missing_nutrients_stay_missing() -> None:
    c = parse_food(usda_food(nutrients={"208": 52.0}))
    assert c is not None and set(c.per_100g) == {"energy_kcal"}


def test_usda_rejects_wrong_units_and_implausible_values() -> None:
    food = usda_food(nutrients={"208": 52.0})
    food["foodNutrients"].append(
        {"nutrientNumber": "203", "unitName": "MG", "value": 5}
    )  # wrong unit
    food["foodNutrients"].append(
        {"nutrientNumber": "204", "unitName": "G", "value": 900}
    )  # > 100 g/100 g
    food["foodNutrients"].append({"nutrientNumber": "205", "unitName": "G", "value": -3})
    c = parse_food(food)
    assert c is not None and set(c.per_100g) == {"energy_kcal"}


def test_usda_energy_atwater_fallback_is_labelled() -> None:
    food = {
        "fdcId": 1,
        "description": "Thing",
        "foodNutrients": [{"nutrientNumber": "957", "unitName": "KCAL", "value": 200}],
    }
    c = parse_food(food)
    assert c is not None and c.per_100g["energy_kcal"] == 200 and c.notes


@pytest.mark.parametrize(
    "food",
    [
        {},
        {"fdcId": 1, "description": "x"},
        {"fdcId": 1, "description": "x", "foodNutrients": []},
        {
            "fdcId": 1,
            "description": "",
            "foodNutrients": [{"nutrientNumber": "208", "unitName": "KCAL", "value": 1}],
        },
    ],
)
def test_usda_unusable_records_are_dropped(food: dict[str, Any]) -> None:
    assert parse_food(food) is None


def test_usda_search_sends_key_only_as_query_param_to_configured_host() -> None:
    seen: list[httpx.Request] = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(req)
        return httpx.Response(200, json={"foods": [usda_food()]})

    out = _usda(handler).search("apple", 5)
    assert len(out) == 1
    assert seen[0].url.host == "fdc.test" and seen[0].url.params["api_key"] == "secret-key"
    assert "Foundation" in seen[0].url.params["dataType"]


@pytest.mark.parametrize(
    ("response", "status"),
    [
        (httpx.Response(429), "rate_limited"),
        (httpx.Response(403), "unavailable"),
        (httpx.Response(500), "unavailable"),
        (httpx.Response(200, text="<html>"), "unavailable"),
        (httpx.Response(200, json={"foods": "nope"}), "unavailable"),
        (httpx.Response(200, json={}), "unavailable"),
    ],
)
def test_usda_errors_are_typed_and_never_leak_the_key(
    response: httpx.Response, status: str
) -> None:
    with pytest.raises(NutritionSourceError) as exc:
        _usda(lambda r: response).search("apple", 5)
    assert exc.value.status == status and "secret-key" not in exc.value.message


def test_usda_timeout_and_network_failure() -> None:
    def slow(req: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("t", request=req)

    def down(req: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("c", request=req)

    with pytest.raises(NutritionSourceError) as t:
        _usda(slow).search("a", 5)
    with pytest.raises(NutritionSourceError) as d:
        _usda(down).search("a", 5)
    assert (t.value.status, d.value.status) == ("timeout", "unavailable")


def test_usda_key_is_not_written_to_logs(caplog: pytest.LogCaptureFixture) -> None:
    from app.core.logging import configure_logging

    configure_logging("INFO")
    caplog.set_level(logging.DEBUG)
    _usda(lambda r: httpx.Response(200, json={"foods": []})).search("apple", 5)
    assert "secret-key" not in caplog.text


# ---- Open Food Facts ----
def test_off_parses_sodium_serving_and_keeps_absent_nutrients_absent() -> None:
    c = parse_product(off_product())
    assert c is not None
    assert c.per_100g["sodium_mg"] == 400.0 and c.serving_grams == 30.0
    assert c.brand == "Acme" and "fiber_g" not in c.per_100g


def test_off_converts_kj_only_energy_and_says_so() -> None:
    c = parse_product({"code": "1", "product_name": "X", "nutriments": {"energy_100g": 418.4}})
    assert c is not None and c.per_100g["energy_kcal"] == pytest.approx(100.0, abs=0.1) and c.notes


def test_off_product_without_nutrients_is_dropped() -> None:
    assert parse_product({"code": "1", "product_name": "X", "nutriments": {}}) is None
    assert parse_product({"code": "1", "nutriments": {"proteins_100g": 1}}) is None


def test_off_serving_without_grams_gives_no_serving_weight() -> None:
    p = off_product()
    p["serving_size"] = "1 biscuit"
    c = parse_product(p)
    assert c is not None and c.serving_grams is None


def test_off_barcode_found_and_not_found() -> None:
    def ok(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": 1, "product": off_product()})

    def none(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": 0})

    assert _off(ok).lookup_barcode("5000112637922") is not None
    assert _off(none).lookup_barcode("5000112637922") is None


def test_off_sends_user_agent_and_maps_errors() -> None:
    seen: list[httpx.Request] = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(req)
        return httpx.Response(200, json={"products": [off_product()]})

    assert len(_off(handler).search("biscuit", 5)) == 1
    assert seen[0].headers["user-agent"] == "Test/1"
    for resp, status in (
        (httpx.Response(429), "rate_limited"),
        (httpx.Response(500), "unavailable"),
    ):
        with pytest.raises(NutritionSourceError) as e:
            _off(lambda r: resp).search("x", 5)  # noqa: B023
        assert e.value.status == status


# ---- local reference table + importer ----
def _csv(tmp_path: Path, text: str) -> Path:
    p = tmp_path / "ref.csv"
    p.write_text(text, encoding="utf-8")
    return p


META = {
    "dataset": "TEST-DS",
    "version": "1",
    "citation": "Test citation",
    "license_note": "Test licence",
}


def test_import_empty_cell_means_not_reported_and_rows_are_traceable(tmp_path: Path) -> None:
    from app.nutrition.sources.local import LocalReferenceSource

    path = _csv(tmp_path, "source_id,name,energy_kcal,protein_g,fat_g\nA1,Test dal,350,22,\n")
    with get_session_factory()() as db:
        res = import_csv(db, path, **META)
        assert (res.inserted, res.errors) == (1, [])
        src = LocalReferenceSource(db)
        assert src.record_count() == 1
        hit = src.search("dal", 5)[0]
    assert hit.per_100g == {"energy_kcal": 350.0, "protein_g": 22.0}  # fat absent, not 0
    assert "TEST-DS" in hit.source_label and hit.source_id == "TEST-DS:A1"
    assert "Test citation" in hit.attribution


def test_import_skips_bad_rows_and_is_idempotent(tmp_path: Path) -> None:
    path = _csv(
        tmp_path,
        "source_id,name,energy_kcal\nA1,Good,100\nA2,Negative,-5\nA3,Text,abc\nA4,Huge,99999\n,NoId,1\n",
    )
    with get_session_factory()() as db:
        first = import_csv(db, path, **META)
        second = import_csv(db, path, **META)
    assert first.inserted == 1 and len(first.errors) == 4
    assert second.inserted == 0 and second.updated == 1


def test_import_requires_provenance_and_known_columns(tmp_path: Path) -> None:
    path = _csv(tmp_path, "source_id,name,energy_kcal\nA1,X,1\n")
    with get_session_factory()() as db:
        with pytest.raises(ValueError):
            import_csv(db, path, **{**META, "citation": " "})
        with pytest.raises(ValueError):
            import_csv(db, _csv(tmp_path, "source_id,name,vitamin_zz\nA,B,1\n"), **META)
        with pytest.raises(ValueError):
            import_csv(db, _csv(tmp_path, "name,energy_kcal\nB,1\n"), **META)


def test_local_search_treats_like_wildcards_literally() -> None:
    from app.nutrition.sources.local import LocalReferenceSource

    with get_session_factory()() as db:
        assert LocalReferenceSource(db).search("%", 5) == []
