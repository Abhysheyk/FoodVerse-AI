"""Extension point for an OPTIONAL, separately validated freshness classifier.

NOTHING IS ENABLED OR SHIPPED HERE. FoodVerse AI does not include, train or endorse a freshness
classifier: no suitable model with a documented dataset and a published evaluation has been
identified for this project, and accuracy is never claimed without that evidence.

If one is added later it must:
* describe itself with complete `ClassifierDocumentation` (model, dataset, evaluation, label set,
  known limitations), which `validate_documentation` enforces before it can be used;
* run as a *separate* signal, shown under its own clearly marked heading with that
  documentation. Its output must never replace the observation-based label, never be shown as a
  safety verdict, and never be turned into a freshness percentage.
"""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class ClassifierDocumentation:
    model_name: str
    version: str
    training_dataset: str  # name + citation/URL of the dataset it was trained on
    evaluation_reference: str  # URL/citation of a published evaluation on held-out data
    labels: tuple[str, ...]  # exactly what the model outputs, in the model's own terms
    foods_covered: tuple[
        str, ...
    ]  # food types it was evaluated on; outside these it is unvalidated
    known_limitations: str


@dataclass(frozen=True)
class ClassifierResult:
    label: str
    documentation: ClassifierDocumentation


class FreshnessClassifier(Protocol):
    documentation: ClassifierDocumentation

    def classify(self, image: bytes, food_category: str) -> ClassifierResult | None:
        """Return a result only for foods the classifier was evaluated on; otherwise None."""
        ...


class UndocumentedClassifierError(ValueError):
    """Raised when a classifier is offered without the evidence required to use it."""


def validate_documentation(doc: ClassifierDocumentation) -> None:
    missing = [
        name
        for name, value in (
            ("model_name", doc.model_name),
            ("version", doc.version),
            ("training_dataset", doc.training_dataset),
            ("evaluation_reference", doc.evaluation_reference),
            ("known_limitations", doc.known_limitations),
        )
        if not value.strip()
    ]
    if not doc.labels:
        missing.append("labels")
    if not doc.foods_covered:
        missing.append("foods_covered")
    if missing:
        raise UndocumentedClassifierError(
            "A freshness classifier cannot be used without documented evidence. Missing: "
            + ", ".join(missing)
        )
