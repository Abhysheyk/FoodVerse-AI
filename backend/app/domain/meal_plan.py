"""Deterministic hard-constraint enforcement for meal plans.

The AI proposes a plan; this module is the boundary that decides whether the plan is
acceptable for this user. Allergies, excluded ingredients and dietary pattern are HARD
constraints: a violation rejects the whole plan (never partially saved). Cooking time and
budget overruns are SOFT warnings and never reject.
"""

import re
from dataclasses import dataclass, field

_WORD = re.compile(r"[a-z0-9']+", re.IGNORECASE)


def _words(text: str) -> set[str]:
    """Lowercase word tokens with light plural stripping, so 'onions' matches 'onion'."""
    words = set()
    for raw in _WORD.findall(text.lower()):
        words.add(raw)
        if len(raw) > 3 and raw.endswith("s"):
            words.add(raw[:-1])
    return words


# Dietary pattern -> ingredients that must be rejected on sight (conservative keyword lists).
DIETARY_FORBIDDEN: dict[str, tuple[str, ...]] = {
    "omnivore": (),
    "vegetarian": (
        "meat", "chicken", "beef", "pork", "lamb", "mutton", "ham", "bacon", "sausage",
        "fish", "salmon", "tuna", "cod", "anchovy", "sardine", "shrimp", "prawn", "crab",
        "lobster", "mussel", "clam", "oyster", "scallop", "squid", "octopus",
        "gelatin", "gelatine", "lard", "tallow", "oyster sauce", "fish sauce", "worcestershire",
    ),
    "vegan": (
        "meat", "chicken", "beef", "pork", "lamb", "mutton", "ham", "bacon", "sausage",
        "fish", "salmon", "tuna", "cod", "anchovy", "sardine", "shrimp", "prawn", "crab",
        "lobster", "mussel", "clam", "oyster", "scallop", "squid", "octopus",
        "gelatin", "gelatine", "lard", "tallow", "oyster sauce", "fish sauce", "worcestershire",
        "egg", "yolk", "white", "mayonnaise", "mayo",
        "milk", "butter", "cheese", "cream", "yogurt", "yoghurt", "curd", "paneer",
        "ghee", "dairy", "khoya", "malai", "whey", "casein", "lactose",
        "honey", "beeswax", "royal jelly",
        "leather",
    ),
    "eggetarian": (
        "meat", "chicken", "beef", "pork", "lamb", "mutton", "ham", "bacon", "sausage",
        "fish", "salmon", "tuna", "cod", "anchovy", "sardine", "shrimp", "prawn", "crab",
        "lobster", "mussel", "clam", "oyster", "scallop", "squid", "octopus",
        "gelatin", "gelatine", "lard", "tallow", "oyster sauce", "fish sauce", "worcestershire",
    ),
    "pescatarian": (
        "meat", "chicken", "beef", "pork", "lamb", "mutton", "ham", "bacon", "sausage",
        "gelatin", "gelatine", "lard", "tallow",
    ),
    "jain": (
        # vegetarian + root vegetables (approximation, clearly advisory)
        "meat", "chicken", "beef", "pork", "lamb", "mutton", "ham", "bacon", "sausage",
        "fish", "salmon", "tuna", "cod", "anchovy", "sardine", "shrimp", "prawn", "crab",
        "lobster", "mussel", "clam", "oyster", "scallop", "squid", "octopus",
        "gelatin", "gelatine", "lard", "tallow", "oyster sauce", "fish sauce", "worcestershire",
        "egg", "yolk", "white", "mayonnaise", "mayo",
        "milk", "butter", "cheese", "cream", "yogurt", "yoghurt", "curd", "paneer",
        "ghee", "dairy", "khoya", "malai", "whey", "casein", "lactose",
        "honey",
        "onion", "garlic", "potato", "carrot", "radish", "beet", "beetroot", "turnip",
        "ginger", "shallot", "leek", "chive", "scallion", "spring onion",
    ),
    "halal": (),  # not enforceable by keyword; surfaced as advisory in the UI
    "kosher": (),  # not enforceable by keyword; surfaced as advisory in the UI
}

# Common allergy declaration -> ingredient keywords that would indicate it.
ALLERGEN_KEYWORDS: dict[str, tuple[str, ...]] = {
    "peanut": ("peanut", "groundnut", "arachis"),
    "tree nut": (
        "almond", "cashew", "walnut", "pistachio", "hazelnut", "pecan", "macadamia",
        "pine nut", "brazil nut", "chestnut",
    ),
    "milk": (
        "milk", "butter", "cheese", "cream", "yogurt", "yoghurt", "curd", "paneer",
        "ghee", "dairy", "khoya", "malai", "whey", "casein",
    ),
    "egg": ("egg", "yolk", "mayonnaise", "mayo"),
    "wheat": (
        "wheat", "flour", "maida", "atta", "semolina", "suji", "bread", "pasta",
        "noodle", "couscous", "bulgur", "seitan",
    ),
    "soy": ("soy", "soya", "tofu", "tempeh", "edamame"),
    "fish": ("fish", "salmon", "tuna", "cod", "anchovy", "sardine", "mackerel", "tilapia"),
    "shellfish": (
        "shrimp", "prawn", "crab", "lobster", "mussel", "clam", "oyster", "scallop",
        "squid", "octopus",
    ),
    "sesame": ("sesame", "tahini", "til"),
    "mustard": ("mustard",),
}

_FISH_SAUCE = frozenset({"fish sauce", "oyster sauce", "worcestershire"})


@dataclass(frozen=True)
class Constraints:
    dietary_pattern: str
    allergies: tuple[str, ...]
    excluded_ingredients: tuple[str, ...]


@dataclass(frozen=True)
class Violation:
    day_date: str
    meal: str
    entry_title: str
    ingredient: str
    code: str  # e.g. "allergy:peanut" | "excluded:onion" | "diet:vegan"
    reason: str

    def to_dict(self) -> dict[str, str]:
        return {
            "day_date": self.day_date,
            "meal": self.meal,
            "entry_title": self.entry_title,
            "ingredient": self.ingredient,
            "code": self.code,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class Warnings:
    cooking_time: list[dict[str, object]] = field(default_factory=list)


def _normalise(text: str) -> str:
    return text.strip().lower()


def _ingredient_matches_keywords(name: str, keywords: tuple[str, ...]) -> str | None:
    name_words = _words(name)
    for kw in keywords:
        kw_words = _words(kw)
        if kw_words and kw_words <= name_words:
            return kw
    return None


def _declared_allergens(allergies: tuple[str, ...]) -> dict[str, tuple[str, ...]]:
    out: dict[str, tuple[str, ...]] = {}
    for declared in allergies:
        key = declared.strip().lower()
        out[key] = ALLERGEN_KEYWORDS.get(key, (key,))
    return out


def find_violations(
    *, days: list[dict[str, object]], constraints: Constraints
) -> list[Violation]:
    """Return every hard-constraint violation. Does not modify the plan."""
    dietary_forbidden = DIETARY_FORBIDDEN.get(constraints.dietary_pattern, ())
    allergen_map = _declared_allergens(constraints.allergies)
    exclusions = tuple(_normalise(x) for x in constraints.excluded_ingredients)

    out: list[Violation] = []
    for day in days:
        day_date = str(day["day_date"])
        for meal in day["meals"]:  # type: ignore[union-attr]
            title = str(meal["title"])  # type: ignore[index]
            cat = str(meal["meal"])  # type: ignore[index]
            for ing in meal["ingredients"]:  # type: ignore[index]
                name = str(ing["name"])  # type: ignore[index]
                lowered = _normalise(name)

                for declared, keywords in allergen_map.items():
                    hit = _ingredient_matches_keywords(lowered, keywords)
                    if hit is not None:
                        out.append(
                            Violation(
                                day_date=day_date,
                                meal=cat,
                                entry_title=title,
                                ingredient=name,
                                code=f"allergy:{declared}",
                                reason=f"Contains a declared allergen ({declared}).",
                            )
                        )

                for excl in exclusions:
                    if excl and (
                        excl in _words(lowered)
                        or _words(excl) <= _words(lowered)
                    ):
                        out.append(
                            Violation(
                                day_date=day_date,
                                meal=cat,
                                entry_title=title,
                                ingredient=name,
                                code=f"excluded:{excl}",
                                reason=f"Contains an excluded ingredient ({excl}).",
                            )
                        )

                if dietary_forbidden:
                    hit = _ingredient_matches_keywords(lowered, dietary_forbidden)
                    if hit is not None:
                        out.append(
                            Violation(
                                day_date=day_date,
                                meal=cat,
                                entry_title=title,
                                ingredient=name,
                                code=f"diet:{constraints.dietary_pattern}",
                                reason=(
                                    f"Contains an ingredient incompatible with the selected "
                                    f"dietary pattern ({constraints.dietary_pattern})."
                                ),
                            )
                        )
    return out


def soft_warnings(
    *, days: list[dict[str, object]], max_cooking_minutes: int | None
) -> Warnings:
    """Cooking time overruns. Advisory only — the plan is still saved."""
    out: list[dict[str, object]] = []
    if max_cooking_minutes is None:
        return Warnings()
    for day in days:
        for meal in day["meals"]:  # type: ignore[union-attr]
            cm = meal.get("cooking_minutes")  # type: ignore[union-attr]
            if isinstance(cm, int) and cm > max_cooking_minutes:
                out.append(
                    {
                        "day_date": day["day_date"],
                        "meal": meal["meal"],  # type: ignore[index]
                        "entry_title": meal["title"],  # type: ignore[index]
                        "cooking_minutes": cm,
                        "max_cooking_minutes": max_cooking_minutes,
                    }
                )
    return Warnings(cooking_time=out)