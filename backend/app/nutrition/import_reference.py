"""Import an offline reference table (such as IFCT) from a CSV file you supply.

    python -m app.nutrition.import_reference foods.csv --dataset "IFCT 2017" --version 2017 \\
        --citation "Longvah T. et al., Indian Food Composition Tables 2017, ICMR-NIN" \\
        --license-note "Used under the dataset's terms; verify before redistribution."

CSV header: source_id,name[,category] followed by any of the nutrient columns
(energy_kcal, protein_g, carbs_g, fat_g, fiber_g, sugars_g, saturated_fat_g, sodium_mg), all per
100 g. An empty cell means "the dataset does not report this" and is stored as absent, never 0.
Rows are upserted by (dataset, source_id); nothing is ever deleted. Dataset, version, citation and
licence note are mandatory so every stored value stays traceable.
"""

import argparse
import csv
import sys
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.reference import ReferenceFood
from app.nutrition.nutrients import NUTRIENT_BY_KEY
from app.nutrition.sources.local import normalise


@dataclass
class ImportResult:
    inserted: int = 0
    updated: int = 0
    errors: list[str] = field(default_factory=list)


def import_csv(
    db: Session, path: Path, *, dataset: str, version: str, citation: str, license_note: str
) -> ImportResult:
    for label, value in (
        ("dataset", dataset),
        ("version", version),
        ("citation", citation),
        ("license note", license_note),
    ):
        if not value.strip():
            raise ValueError(f"A non-empty {label} is required so every value stays traceable.")

    result = ImportResult()
    with path.open(newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        columns = set(reader.fieldnames or [])
        allowed = {"source_id", "name", "category", *NUTRIENT_BY_KEY}
        unknown = columns - allowed
        if unknown:
            raise ValueError(f"Unknown columns: {sorted(unknown)}")
        if not {"source_id", "name"} <= columns:
            raise ValueError("The CSV needs 'source_id' and 'name' columns.")

        for line, row in enumerate(reader, start=2):
            source_id = (row.get("source_id") or "").strip()
            name = (row.get("name") or "").strip()
            if not source_id or not name:
                result.errors.append(f"line {line}: source_id and name are required")
                continue
            nutrients: dict[str, float] = {}
            bad = False
            for key in NUTRIENT_BY_KEY:
                raw = (row.get(key) or "").strip()
                if raw == "":
                    continue
                try:
                    number = float(raw)
                except ValueError:
                    result.errors.append(f"line {line}: {key} is not a number")
                    bad = True
                    break
                if not 0 <= number <= NUTRIENT_BY_KEY[key].max_per_100g:
                    result.errors.append(f"line {line}: {key} is out of range")
                    bad = True
                    break
                nutrients[key] = number
            if bad:
                continue
            if not nutrients:
                result.errors.append(f"line {line}: no nutrient values")
                continue

            existing = db.scalar(
                select(ReferenceFood).where(
                    ReferenceFood.dataset == dataset, ReferenceFood.source_id == source_id
                )
            )
            category = (row.get("category") or "").strip() or None
            if existing is None:
                db.add(
                    ReferenceFood(
                        dataset=dataset,
                        dataset_version=version,
                        source_id=source_id,
                        name=name[:200],
                        name_normalized=normalise(name)[:200],
                        category=category,
                        nutrients=nutrients,
                        citation=citation,
                        license_note=license_note,
                    )
                )
                result.inserted += 1
            else:
                existing.dataset_version = version
                existing.name = name[:200]
                existing.name_normalized = normalise(name)[:200]
                existing.category = category
                existing.nutrients = nutrients
                existing.citation = citation
                existing.license_note = license_note
                result.updated += 1
    db.commit()
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("csv_file", type=Path)
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--citation", required=True)
    parser.add_argument("--license-note", required=True)
    args = parser.parse_args(argv)

    from app.db.session import get_session_factory

    with get_session_factory()() as db:
        try:
            result = import_csv(
                db,
                args.csv_file,
                dataset=args.dataset,
                version=args.version,
                citation=args.citation,
                license_note=args.license_note,
            )
        except (ValueError, OSError) as exc:
            print(f"Import failed: {exc}", file=sys.stderr)
            return 1
    print(f"Inserted {result.inserted}, updated {result.updated}, skipped {len(result.errors)}.")
    for err in result.errors[:20]:
        print(f"  - {err}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
