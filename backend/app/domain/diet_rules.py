"""Deterministic allergen and diet rules.

This is the enforcement layer: a model cannot talk its way past it. Matching is on whole
normalised words so 'flour' does not match 'cauliflower'. The keyword tables are deliberately
conservative and small enough to review; they are not a regulatory allergen classification.
"""

import re
from dataclasses import dataclass

_WORD = re.compile(r"[a-z0-9']+")

# canonical allergen -> ingredient keywords that indicate it
ALLERGEN_KEYWORDS: dict[str, tuple[str, ...]] = {
    "peanut": ("peanut", "peanuts", "groundnut", "groundnuts"),
    "tree nut": (
        "almond", "almonds", "cashew", "cashews", "walnut", "walnuts", "pistachio",
        "pistachios", "hazelnut", "hazelnuts", "pecan", "pecans", "macadamia",
    ),
    "milk": (
        "milk", "butter", "buttermilk", "ghee", "cheese", "cream", "yoghurt", "yogurt",
        "paneer", "khoya", "kheer", "curd",
    ),
    "egg": ("egg", "eggs", "mayonnaise", "mayo", "omelette", "omelet"),
    "wheat": (
        "wheat", "flour", "maida", "atta", "bread", "breadcrumbs", "pasta", "spaghetti",
        "noodle", "noodles", "semolina", "sooji", "rava", "couscous", "malt",
    ),
    "soy": ("soy", "soya", "tofu", "tempeh", "edamame", "soybean", "soybeans"),
    "fish": ("fish", "salmon", "tuna", "cod", "tilapia", "anchovy", "anchovies", "sardine", "sardines", "mackerel"),
    "shellfish": (
        "shrimp", "prawn", "prawns", "crab", "lobster", "mussel", "mussels", "oyster",
        "oysters", "squid", "calamari", "clam", "clams", "scallop", "scallops",
    ),
    "sesame": ("sesame", "tahini", "til"),
    "mustard": ("mustard",),
}

MEAT = (
    "chicken", "beef", "pork", "lamb", "mutton", "goat", "bacon", "ham", "sausage",
    "salami", "pepperoni", "turkey", "duck", "venison", "meat", "mince", "steak",
)
SEAFOOD = ALLERGEN_KEYWORDS["fish"] + ALLERGEN_KEYWORDS["shellfish"]
ANIMAL_PRODUCT = ALLERGEN_KEYWORDS["milk"] + ALLERGEN_KEYWORDS["egg"] + ("honey", "gelatin")
ROOT_VEG = ("onion", "onions", "garlic", "potato", "potatoes", "carrot", "carrots", "radish", "beetroot", "beet")

DIET_FORBIDDEN: dict[str, tuple[str, ...]] = {
    "vegetarian": MEAT + SEAFOOD,
    "eggetarian": MEAT + SEAFOOD,
    "vegan": MEAT + SEAFOOD + ANIMAL_PRODUCT,
    "pescatarian": MEAT,
    "jain": MEAT + SEAFOOD + ROOT_VEG,
    "gluten_free": ALLERGEN_KEYWORDS["wheat"] + ("barley", "rye", "soy sauce"),
    "lactose_free": ALLERGEN_KEYWORDS["milk"],
}

# Diets a keyword table cannot verify. Recorded as an explicit caution, never silently accepted.
UNVERIFIABLE_DIETS: frozenset[str] = frozenset({"halal", "kosher"})

DIET_LABELS: dict[str, str] = {
    "vegetarian": "vegetarian",
    "eggetarian": "eggetarian",
    "vegan": "vegan",
    "pescatarian": "pescatarian",
    "jain": "Jain",
    "gluten_free": "gluten-free",
    "lactose_free": "lactose-free",
    "halal": "halal",
    "kosher": "kosher",
}


def _haystack(*texts: str) -> str:
    words = [w for text in texts for w in _WORD.findall(text.casefold())]
    return " " + " ".join(words) + " "


def _hits(hay: str, keywords: tuple[str, ...]) -> list[str]:
    return [k for k in keywords if f" {k} " in hay]


@dataclass(frozen=True)
class Conflict:
    kind: str  # "allergy" | "diet"
    rule: str  # the user's allergen or diet
    ingredient: str  # the offending ingredient name (or the recipe title)
    matched: str  # the keyword that matched

    @property
    def message(self) -> str:
        label = f"your {self.rule} allergy" if self.kind == "allergy" else self.rule
        return f"“{self.ingredient}” contains “{self.matched}”, which conflicts with {label}."


def check_recipe(
    title: str, ingredient_names: list[str], allergies: list[str], diets: list[str]
) -> list[Conflict]:
    """Return every hard-constraint violation. Empty means the recipe is allowed."""
    conflicts: list[Conflict] = []
    for name in ingredient_names:
        hay = _haystack(name)
        for allergy in allergies:
            keywords = ALLERGEN_KEYWORDS.get(allergy.casefold())
            if keywords:
                for matched in _hits(hay, keywords):
                    conflicts.append(Conflict("allergy", allergy, name, matched))
        for diet in diets:
            keywords = DIET_FORBIDDEN.get(diet.casefold())
            if keywords:
                for matched in _hits(hay, keywords):
                    conflicts.append(Conflict("diet", diet, name, matched))
    # dedupe while preserving order
    seen: set[tuple[str, str, str, str]] = set()
    unique: list[Conflict] = []
    for c in conflicts:
        key = (c.kind, c.rule, c.ingredient, c.matched)
        if key not in seen:
            seen.add(key)
            unique.append(c)
    return unique


def declared_but_unverifiable(diets: list[str]) -> list[str]:
    return [d for d in diets if d.casefold() in UNVERIFIABLE_DIETS]


def allergens_present(ingredient_names: list[str]) -> list[str]:
    """Allergens detected from ingredient names (independent of the user's own declarations)."""
    found: list[str] = []
    hay = _haystack(*ingredient_names)
    for allergen, keywords in ALLERGEN_KEYWORDS.items():
        if _hits(hay, keywords):
            found.append(allergen)
    return found