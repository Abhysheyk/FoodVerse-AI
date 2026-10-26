"""Offline reference tables imported by the operator (e.g. IFCT).

See app/nutrition/import_reference.py for how a table is imported.
"""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.reference import ReferenceFood
from app.nutrition.nutrients import NUTRIENT_BY_KEY
from app.nutrition.types import FoodCandidate


def normalise(text: str) -> str:
    return " ".join(text.casefold().split())


def _escape_like(token: str) -> str:
    return token.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


class LocalReferenceSource:
    name = "local_reference"
    label = "Local reference table"

    def __init__(self, db: Session) -> None:
        self._db = db

    def record_count(self) -> int:
        return self._db.scalar(select(func.count()).select_from(ReferenceFood)) or 0

    def search(self, query: str, limit: int) -> list[FoodCandidate]:
        tokens = normalise(query).split()
        if not tokens:
            return []
        stmt = select(ReferenceFood)
        for token in tokens:
            stmt = stmt.where(
                ReferenceFood.name_normalized.like(f"%{_escape_like(token)}%", escape="\\")
            )
        rows = self._db.scalars(
            stmt.order_by(func.length(ReferenceFood.name_normalized), ReferenceFood.name).limit(
                limit
            )
        ).all()
        results: list[FoodCandidate] = []
        for row in rows:
            per_100g = {
                k: float(v)
                for k, v in row.nutrients.items()
                if k in NUTRIENT_BY_KEY and isinstance(v, int | float)
            }
            if not per_100g:
                continue
            results.append(
                FoodCandidate(
                    source="local_reference",
                    source_label=f"{row.dataset} ({row.dataset_version})",
                    source_id=f"{row.dataset}:{row.source_id}",
                    name=row.name,
                    data_type="Reference table (offline)",
                    per_100g=per_100g,
                    attribution=f"{row.citation} {row.license_note}".strip(),
                )
            )
        return results
