"""Looks foods up in the configured trusted sources. This is the only place nutrient values
enter the system: they come straight from a source record, never from a model."""

import re
from dataclasses import dataclass
from typing import Literal

import httpx
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.nutrition.nutrients import NUTRIENTS
from app.nutrition.sources.base import NutritionSource
from app.nutrition.sources.local import LocalReferenceSource
from app.nutrition.sources.off import OpenFoodFactsSource
from app.nutrition.sources.usda import UsdaFdcSource
from app.nutrition.types import FoodCandidate, NutritionSourceError
from app.schemas.food import NutrientDefinition, NutritionStatus, SourceStatus

SourceState = Literal["ok", "not_configured", "unavailable", "rate_limited", "timeout"]
_NON_WORD = re.compile(r"[^\w\s'&-]", re.UNICODE)


def clean_query(query: str) -> str:
    return " ".join(_NON_WORD.sub(" ", query).split())[:80]


@dataclass
class SearchOutcome:
    results: list[FoodCandidate]
    sources: list[SourceStatus]


class NutritionService:
    def __init__(
        self,
        local: LocalReferenceSource,
        usda: NutritionSource | None,
        off: OpenFoodFactsSource | None,
    ) -> None:
        self._local = local
        self._usda = usda
        self._off = off

    def _not_configured(self, name: str, label: str, how: str) -> SourceStatus:
        return SourceStatus(source=name, label=label, status="not_configured", message=how)

    def status(self) -> NutritionStatus:
        records = self._local.record_count()
        sources = [
            SourceStatus(
                source="local_reference",
                label=self._local.label,
                status="ok" if records else "not_configured",
                message=None
                if records
                else "No reference table has been imported (see README: import_reference).",
            ),
            SourceStatus(source="usda_fdc", label="USDA FoodData Central", status="ok")
            if self._usda
            else self._not_configured(
                "usda_fdc", "USDA FoodData Central", "Set USDA_FDC_API_KEY to enable."
            ),
            SourceStatus(source="open_food_facts", label="Open Food Facts", status="ok")
            if self._off
            else self._not_configured(
                "open_food_facts", "Open Food Facts", "Set OPEN_FOOD_FACTS_ENABLED=true to enable."
            ),
        ]
        return NutritionStatus(
            sources=sources,
            nutrients=[
                NutrientDefinition(key=n.key, label=n.label, unit=n.unit, core=n.core)
                for n in NUTRIENTS
            ],
            any_configured=records > 0 or self._usda is not None or self._off is not None,
            local_reference_records=records,
        )

    def search(self, query: str, limit: int = 8) -> SearchOutcome:
        query = clean_query(query)
        results: list[FoodCandidate] = []
        statuses: list[SourceStatus] = []

        records = self._local.record_count()
        if records:
            results.extend(self._local.search(query, limit))
            statuses.append(
                SourceStatus(source="local_reference", label=self._local.label, status="ok")
            )
        else:
            statuses.append(
                self._not_configured(
                    "local_reference", self._local.label, "No reference table imported."
                )
            )

        for name, label, source, how in (
            ("usda_fdc", "USDA FoodData Central", self._usda, "Set USDA_FDC_API_KEY to enable."),
            ("open_food_facts", "Open Food Facts", self._off, "Set OPEN_FOOD_FACTS_ENABLED=true."),
        ):
            if source is None:
                statuses.append(self._not_configured(name, label, how))
                continue
            try:
                results.extend(source.search(query, limit))
                statuses.append(SourceStatus(source=name, label=label, status="ok"))
            except NutritionSourceError as exc:
                state: SourceState = exc.status  # type: ignore[assignment]
                statuses.append(
                    SourceStatus(source=name, label=label, status=state, message=exc.message)
                )
        return SearchOutcome(results=results, sources=statuses)

    def barcode(self, barcode: str) -> tuple[FoodCandidate | None, list[SourceStatus]]:
        if self._off is None:
            return None, [
                self._not_configured(
                    "open_food_facts", "Open Food Facts", "Set OPEN_FOOD_FACTS_ENABLED=true."
                )
            ]
        try:
            found = self._off.lookup_barcode(barcode)
        except NutritionSourceError as exc:
            state: SourceState = exc.status  # type: ignore[assignment]
            return None, [
                SourceStatus(
                    source="open_food_facts",
                    label="Open Food Facts",
                    status=state,
                    message=exc.message,
                )
            ]
        return found, [SourceStatus(source="open_food_facts", label="Open Food Facts", status="ok")]


def build_nutrition_service(
    settings: Settings, db: Session, transport: httpx.BaseTransport | None = None
) -> NutritionService:
    usda = None
    if settings.usda_fdc_api_key is not None:
        usda = UsdaFdcSource(
            settings.usda_fdc_api_key.get_secret_value(),
            settings.usda_fdc_base_url,
            settings.nutrition_timeout_seconds,
            transport,
        )
    off = None
    if settings.open_food_facts_enabled:
        off = OpenFoodFactsSource(
            settings.open_food_facts_base_url,
            settings.open_food_facts_user_agent,
            settings.nutrition_timeout_seconds,
            transport,
        )
    return NutritionService(LocalReferenceSource(db), usda, off)
