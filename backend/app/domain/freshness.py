"""Deterministic freshness/spoilage-sign assessment rules.

The vision model contributes **only evidence**: what it can see (colour changes, mould-like
growth, ...) and how usable the image is. Everything the user is told about it - the label, the
advice level, the reasons, the next steps and the food-specific cautions - is produced here, from
fixed rules and fixed text, so it can be reviewed, tested and cannot be "talked into" a
reassurance by a model or by text inside a photo.

Hard rules:
* There is no "safe" outcome. The best label is "no obvious visible concern in this image", and
  the guidance that accompanies it always says appearance cannot confirm safety.
* No percentage, score or probability of any kind.
* Missing, unclear or contradictory evidence yields "inconclusive", never a guess.
"""

import enum
from dataclasses import dataclass, field
from datetime import date


class FoodCategory(enum.StrEnum):
    FRUIT = "fruit"
    VEGETABLES = "vegetables"
    LEAFY_GREENS = "leafy_greens"
    MEAT_POULTRY = "meat_poultry"
    FISH_SEAFOOD = "fish_seafood"
    DAIRY_EGGS = "dairy_eggs"
    COOKED_FOOD = "cooked_food"
    BREAD_BAKED = "bread_baked"
    PACKAGED_SHELF_STABLE = "packaged_shelf_stable"
    OTHER = "other"


CATEGORY_LABELS: dict[FoodCategory, str] = {
    FoodCategory.FRUIT: "Fruit",
    FoodCategory.VEGETABLES: "Vegetables",
    FoodCategory.LEAFY_GREENS: "Leafy greens and herbs",
    FoodCategory.MEAT_POULTRY: "Meat and poultry",
    FoodCategory.FISH_SEAFOOD: "Fish and seafood",
    FoodCategory.DAIRY_EGGS: "Dairy and eggs",
    FoodCategory.COOKED_FOOD: "Cooked food and leftovers (including rice)",
    FoodCategory.BREAD_BAKED: "Bread and baked goods",
    FoodCategory.PACKAGED_SHELF_STABLE: "Packaged / tinned / shelf-stable food",
    FoodCategory.OTHER: "Something else",
}

# Foods where appearance is a poor guide and time/temperature matters most.
HIGH_RISK: frozenset[FoodCategory] = frozenset(
    {
        FoodCategory.MEAT_POULTRY,
        FoodCategory.FISH_SEAFOOD,
        FoodCategory.DAIRY_EGGS,
        FoodCategory.COOKED_FOOD,
    }
)


class StorageCondition(enum.StrEnum):
    REFRIGERATOR = "refrigerator"
    FREEZER = "freezer"
    ROOM_TEMPERATURE = "room_temperature"
    UNKNOWN = "unknown"


class Packaging(enum.StrEnum):
    SEALED_UNOPENED = "sealed_unopened"
    OPENED = "opened"
    UNPACKAGED = "unpackaged"
    UNKNOWN = "unknown"


class VisualLabel(enum.StrEnum):
    VISIBLE_CONCERN = "visible_concern_observed"
    NO_OBVIOUS_CONCERN = "no_obvious_visible_concern"
    INCONCLUSIVE = "inconclusive"


LABEL_TEXT: dict[VisualLabel, str] = {
    VisualLabel.VISIBLE_CONCERN: "Visible concern observed",
    VisualLabel.NO_OBVIOUS_CONCERN: "No obvious visible concern in this image",
    VisualLabel.INCONCLUSIVE: "Inconclusive",
}


class AdviceLevel(enum.StrEnum):
    DISCARD = "discard_recommended"
    CAUTION = "use_caution"
    GENERAL = "general_caution"


class Feature(enum.StrEnum):
    DISCOLORATION = "discoloration"
    BRUISING = "bruising"
    WILTING = "wilting"
    MOLD_LIKE_GROWTH = "mold_like_growth"
    SURFACE_CHANGE = "surface_change"  # slimy/wet/dry/cracked/crystallised surface
    VISIBLE_DAMAGE = "visible_damage"  # cuts, punctures, leaks, swollen or dented packs
    OTHER = "other_visible_change"


class ImageQuality(enum.StrEnum):
    CLEAR = "clear"
    LIMITED = "limited"
    UNUSABLE = "unusable"


FOOD_MATCH = ("yes", "no", "unsure")


@dataclass(frozen=True)
class ObservedSign:
    feature: Feature
    description: str
    location: str
    severity: str  # "slight" | "moderate" | "marked": the model's own words
    certainty: str  # "clearly_visible" | "possibly_visible": the model's own words


@dataclass(frozen=True)
class ImageEvidence:
    image_quality: ImageQuality
    food_visible: bool
    matches_confirmed_food: str  # "yes" | "no" | "unsure"
    observations: tuple[ObservedSign, ...]


@dataclass(frozen=True)
class Context:
    category: FoodCategory
    storage: StorageCondition
    packaging: Packaging
    storage_hours: int | None
    use_by: date | None
    best_before: date | None
    assessed_on: date


@dataclass(frozen=True)
class Reason:
    code: str
    text: str


@dataclass(frozen=True)
class Assessment:
    label: VisualLabel
    inconclusive_reasons: tuple[Reason, ...]
    advice_level: AdviceLevel
    advice_reasons: tuple[Reason, ...]
    steps: tuple[str, ...]
    category_cautions: tuple[str, ...]
    retake_tips: tuple[str, ...] = field(default_factory=tuple)


INCONCLUSIVE_TEXT: dict[str, str] = {
    "image_not_analysed": "The image was not analysed, so nothing could be observed.",
    "no_food_visible": "The model did not see food in this image.",
    "image_unusable": "The image is too unclear (dark, blurred, far away or glared) to judge.",
    "food_mismatch": "The image does not appear to show the food you named.",
    "image_limited": (
        "The image quality is limited, so the absence of visible changes means little."
    ),
    "food_match_unsure": "The model could not tell whether the image shows the food you named.",
}

# Fixed, reviewed wording. Commonly published food-safety advice (e.g. USDA FSIS,
# foodsafety.gov); rules differ by country, so users are pointed to official sources.
GUIDANCE_SOURCES: tuple[tuple[str, str], ...] = (
    ("FoodSafety.gov", "https://www.foodsafety.gov"),
    ("USDA Food Safety and Inspection Service", "https://www.fsis.usda.gov"),
)

GENERAL_NOTES: tuple[str, ...] = (
    "A photo only shows surfaces. Harmful bacteria, toxins and other microbes are often "
    "invisible, odourless and tasteless, so food can look fine and still make you ill.",
    "This result describes what is visible in one image. It is not a statement that the food "
    "is safe, or unsafe, to eat.",
    "When in doubt, throw it out. If the food would be eaten by someone pregnant, very young, "
    "older, or with a weakened immune system, or if anyone becomes unwell after eating it, "
    "speak to a qualified professional (doctor, pharmacist or your local food-safety authority).",
)

RETAKE_TIPS: tuple[str, ...] = (
    "Use bright, even light (daylight is best) and avoid glare and shadows.",
    "Take a sharp close-up of the surface, then another from a different side.",
    "Include any label or date on the packaging in a separate photo.",
)

CATEGORY_CAUTIONS: dict[FoodCategory, tuple[str, ...]] = {
    FoodCategory.FRUIT: (
        "Bruises and soft spots mostly affect quality. Spreading soft areas, leaking juice, "
        "fermented smells or any mould are reasons to discard, especially for soft or juicy "
        "fruit, where mould can spread beyond what you can see.",
    ),
    FoodCategory.VEGETABLES: (
        "Surface blemishes alone do not tell you whether vegetables are unsafe, but sliminess, "
        "mushy or leaking areas and mould are reasons to discard. Cut or cooked vegetables are "
        "more perishable than whole ones.",
    ),
    FoodCategory.LEAFY_GREENS: (
        "Wilting mainly affects quality, but slimy, mushy or mouldy leaves should be discarded. "
        "Washing does not reliably remove harmful bacteria from leafy greens.",
    ),
    FoodCategory.MEAT_POULTRY: (
        "Spoilage and harmful bacteria in raw or cooked meat and poultry often cannot be seen or "
        "smelled. Judge by safe handling (kept cold, within its date, cooked thoroughly), not by "
        "appearance. Raw meat left out for more than 2 hours (1 hour in hot weather) should be "
        "discarded.",
    ),
    FoodCategory.FISH_SEAFOOD: (
        "Appearance is an unreliable guide for fish and seafood. Some toxins (for example "
        "histamine in some fish) are not destroyed by cooking and cannot be seen or smelled. "
        "Keep it cold, respect its date, and discard if it was left out for more than 2 hours.",
    ),
    FoodCategory.DAIRY_EGGS: (
        "Do not rely on appearance for dairy or eggs. Mould on soft dairy such as yoghurt or soft "
        "cheese means the whole item should be discarded. Discard cracked or dirty-shelled eggs.",
    ),
    FoodCategory.COOKED_FOOD: (
        "Cooked rice and leftovers can carry bacteria whose toxins are not destroyed by "
        "reheating and do not change how the food looks. Refrigerate within 2 hours of cooking "
        "and eat within about 3 to 4 days.",
    ),
    FoodCategory.BREAD_BAKED: (
        "Mould on bread and baked goods grows through the whole item, not just where you see it. "
        "Discard the entire item, and do not sniff it.",
    ),
    FoodCategory.PACKAGED_SHELF_STABLE: (
        "Swollen, leaking, badly dented or rusted tins and puffed or damaged packs should be "
        "discarded without tasting. A photo of the outside may not show this, so also check the "
        "pack in person and the date.",
    ),
    FoodCategory.OTHER: (
        "Without specific guidance for this food, treat any visible change, unusual smell or "
        "doubtful storage history as a reason to discard it.",
    ),
}

_STEPS_DISCARD: tuple[str, ...] = (
    "Do not eat it, and do not taste or sniff it to check.",
    "Throw it away in a sealed bag where children and pets cannot reach it.",
    "Wash your hands and any container, board or surface that touched it with hot soapy water.",
)
_STEP_MOLD = (
    "Mould can spread through soft or porous food where you cannot see it, so cutting away the "
    "visible patch is not a reliable fix."
)
_STEPS_CAUTION: tuple[str, ...] = (
    "Do not rely on how the food looks or smells. Check its date and how it was stored.",
    "If you cannot confirm it was stored safely and is within date, the safer choice is to "
    "discard it.",
    "Do not serve it to anyone at higher risk (pregnant, young children, older people, weakened "
    "immunity).",
)
_STEPS_GENERAL: tuple[str, ...] = (
    "No visible concern in a photo does not make the food safe. Check its date and storage "
    "history, and follow the guidance for this type of food below.",
    "If anything about its smell, texture, packaging or storage history seems off, discard it.",
)

_HOURS_ROOM_TEMP_LIMIT = 2
_COOKED_FRIDGE_LIMIT_HOURS = 4 * 24


def _label_for(evidence: ImageEvidence | None) -> tuple[VisualLabel, tuple[Reason, ...]]:
    def reasons(*codes: str) -> tuple[Reason, ...]:
        return tuple(Reason(c, INCONCLUSIVE_TEXT[c]) for c in codes)

    if evidence is None:
        return VisualLabel.INCONCLUSIVE, reasons("image_not_analysed")
    blocking: list[str] = []
    if not evidence.food_visible:
        blocking.append("no_food_visible")
    if evidence.image_quality is ImageQuality.UNUSABLE:
        blocking.append("image_unusable")
    if evidence.matches_confirmed_food == "no":
        blocking.append("food_mismatch")
    if blocking:
        return VisualLabel.INCONCLUSIVE, reasons(*blocking)
    if evidence.observations:
        return VisualLabel.VISIBLE_CONCERN, ()
    if evidence.image_quality is ImageQuality.CLEAR and evidence.matches_confirmed_food == "yes":
        return VisualLabel.NO_OBVIOUS_CONCERN, ()
    soft: list[str] = []
    if evidence.image_quality is not ImageQuality.CLEAR:
        soft.append("image_limited")
    if evidence.matches_confirmed_food == "unsure":
        soft.append("food_match_unsure")
    return VisualLabel.INCONCLUSIVE, reasons(*soft)


def assess(evidence: ImageEvidence | None, ctx: Context) -> Assessment:
    """Combine image evidence (may be None) with what the user told us. Pure and deterministic."""
    label, inconclusive = _label_for(evidence)
    high_risk = ctx.category in HIGH_RISK
    discard: list[Reason] = []
    caution: list[Reason] = []

    has_mold = bool(evidence) and any(
        o.feature is Feature.MOLD_LIKE_GROWTH for o in (evidence.observations if evidence else ())
    )
    if has_mold:
        discard.append(
            Reason(
                "mold_like_growth",
                "Mould-like growth was reported in the image (it may be certain or only "
                "possible). Mould can be accompanied by toxins and root deep into food.",
            )
        )
    if high_risk and label is VisualLabel.VISIBLE_CONCERN and not has_mold:
        discard.append(
            Reason(
                "visible_change_high_risk_food",
                "A visible change was reported on a food type where spoilage and harmful "
                "bacteria are a particular concern.",
            )
        )
    if (
        high_risk
        and ctx.storage is StorageCondition.ROOM_TEMPERATURE
        and ctx.storage_hours is not None
        and ctx.storage_hours > _HOURS_ROOM_TEMP_LIMIT
    ):
        discard.append(
            Reason(
                "left_out_too_long",
                "You said it was kept at room temperature for more than 2 hours. Perishable "
                "food left out that long should be discarded.",
            )
        )
    if (
        ctx.category is FoodCategory.COOKED_FOOD
        and ctx.storage is StorageCondition.REFRIGERATOR
        and ctx.storage_hours is not None
        and ctx.storage_hours > _COOKED_FRIDGE_LIMIT_HOURS
    ):
        discard.append(
            Reason(
                "leftovers_too_old",
                "Cooked leftovers kept in the fridge for more than about 4 days are beyond "
                "commonly published guidance.",
            )
        )
    if ctx.use_by is not None and ctx.use_by < ctx.assessed_on:
        entry = Reason(
            "use_by_passed",
            "The use-by date you entered has passed. Use-by dates relate to safety for "
            "perishable foods.",
        )
        (discard if high_risk else caution).append(entry)
    if ctx.best_before is not None and ctx.best_before < ctx.assessed_on:
        caution.append(
            Reason(
                "best_before_passed",
                "The best-before date you entered has passed. This is mainly a quality date, "
                "but check the food carefully and its storage history.",
            )
        )
    if label is VisualLabel.VISIBLE_CONCERN and not discard:
        caution.append(Reason("visible_concern", "A visible change was reported in the image."))
    if label is VisualLabel.INCONCLUSIVE:
        caution.append(
            Reason("inconclusive", "The image could not settle whether there is a visible concern.")
        )
    if high_risk and ctx.storage is StorageCondition.UNKNOWN:
        caution.append(
            Reason(
                "storage_unknown",
                "How this perishable food was stored is unknown, and storage matters more than "
                "appearance for this type of food.",
            )
        )

    if discard:
        level, reasons = AdviceLevel.DISCARD, tuple(discard + caution)
        steps = _STEPS_DISCARD + ((_STEP_MOLD,) if has_mold else ())
    elif caution:
        level, reasons = AdviceLevel.CAUTION, tuple(caution)
        steps = _STEPS_CAUTION
    else:
        level, reasons = AdviceLevel.GENERAL, ()
        steps = _STEPS_GENERAL

    return Assessment(
        label=label,
        inconclusive_reasons=inconclusive,
        advice_level=level,
        advice_reasons=reasons,
        steps=steps,
        category_cautions=CATEGORY_CAUTIONS[ctx.category],
        retake_tips=RETAKE_TIPS if label is VisualLabel.INCONCLUSIVE else (),
    )
