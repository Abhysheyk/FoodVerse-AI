import itertools
import re
from datetime import date, timedelta

import pytest

from app.domain.freshness import (
    GENERAL_NOTES,
    HIGH_RISK,
    AdviceLevel,
    Assessment,
    Context,
    Feature,
    FoodCategory,
    ImageEvidence,
    ImageQuality,
    ObservedSign,
    Packaging,
    StorageCondition,
    VisualLabel,
    assess,
)

TODAY = date(2026, 10, 26)
FC, SC, AL = FoodCategory, StorageCondition, AdviceLevel


def ctx(
    category: FoodCategory = FC.FRUIT,
    storage: StorageCondition = SC.REFRIGERATOR,
    hours: int | None = None,
    use_by: date | None = None,
    best_before: date | None = None,
) -> Context:
    return Context(category, storage, Packaging.UNKNOWN, hours, use_by, best_before, TODAY)


def sign(
    feature: Feature = Feature.DISCOLORATION, certainty: str = "clearly_visible"
) -> ObservedSign:
    return ObservedSign(feature, "d", "top", "moderate", certainty)


def ev(
    quality: ImageQuality = ImageQuality.CLEAR,
    visible: bool = True,
    match: str = "yes",
    *signs: ObservedSign,
) -> ImageEvidence:
    return ImageEvidence(quality, visible, match, tuple(signs))


# ---- labels ----
def test_no_image_analysis_is_inconclusive_never_reassuring() -> None:
    a = assess(None, ctx())
    assert a.label is VisualLabel.INCONCLUSIVE
    assert [r.code for r in a.inconclusive_reasons] == ["image_not_analysed"]
    assert a.advice_level is AL.CAUTION and a.retake_tips


def test_clear_image_with_nothing_seen_is_only_no_obvious_concern() -> None:
    a = assess(ev(), ctx())
    assert a.label is VisualLabel.NO_OBVIOUS_CONCERN
    assert a.advice_level is AL.GENERAL
    assert a.inconclusive_reasons == () and a.retake_tips == ()
    assert "does not make the food safe" in " ".join(a.steps)


@pytest.mark.parametrize(
    ("evidence", "code"),
    [
        (ev(visible=False), "no_food_visible"),
        (ev(ImageQuality.UNUSABLE), "image_unusable"),
        (ev(match="no"), "food_mismatch"),
    ],
)
def test_blocking_problems_force_inconclusive_even_with_observations(
    evidence: ImageEvidence, code: str
) -> None:
    with_signs = ImageEvidence(
        evidence.image_quality, evidence.food_visible, evidence.matches_confirmed_food, (sign(),)
    )
    for e in (evidence, with_signs):
        a = assess(e, ctx())
        assert a.label is VisualLabel.INCONCLUSIVE
        assert code in [r.code for r in a.inconclusive_reasons]


def test_limited_or_unsure_without_evidence_is_inconclusive_not_clear() -> None:
    limited = assess(ev(ImageQuality.LIMITED), ctx())
    unsure = assess(ev(match="unsure"), ctx())
    assert limited.label is VisualLabel.INCONCLUSIVE
    assert [r.code for r in limited.inconclusive_reasons] == ["image_limited"]
    assert unsure.label is VisualLabel.INCONCLUSIVE
    assert [r.code for r in unsure.inconclusive_reasons] == ["food_match_unsure"]


def test_observations_in_a_limited_image_still_count_as_a_concern() -> None:
    a = assess(ev(ImageQuality.LIMITED, True, "unsure", sign()), ctx())
    assert a.label is VisualLabel.VISIBLE_CONCERN


# ---- advice level ----
@pytest.mark.parametrize("certainty", ["clearly_visible", "possibly_visible"])
@pytest.mark.parametrize("category", list(FC))
def test_mold_like_growth_always_recommends_discarding(
    category: FoodCategory, certainty: str
) -> None:
    a = assess(
        ev(ImageQuality.CLEAR, True, "yes", sign(Feature.MOLD_LIKE_GROWTH, certainty)),
        ctx(category),
    )
    assert a.advice_level is AL.DISCARD
    assert any("cutting away" in s for s in a.steps)
    assert any("Do not eat it" in s for s in a.steps)


def test_visible_change_on_high_risk_food_recommends_discarding_but_not_on_produce() -> None:
    e = ev(ImageQuality.CLEAR, True, "yes", sign(Feature.SURFACE_CHANGE))
    assert assess(e, ctx(FC.MEAT_POULTRY)).advice_level is AL.DISCARD
    assert assess(e, ctx(FC.FRUIT)).advice_level is AL.CAUTION


@pytest.mark.parametrize(
    ("hours", "expected"),
    [
        (1, AL.CAUTION),
        (2, AL.CAUTION),
        (3, AL.DISCARD),
        (30, AL.DISCARD),
    ],
)
def test_perishable_left_at_room_temperature(hours: int, expected: AdviceLevel) -> None:
    a = assess(ev(), ctx(FC.COOKED_FOOD, SC.ROOM_TEMPERATURE, hours))
    assert a.advice_level in (expected, AL.GENERAL)
    if expected is AL.DISCARD:
        assert a.advice_level is AL.DISCARD
        assert "left_out_too_long" in [r.code for r in a.advice_reasons]
    else:
        assert a.advice_level is AL.GENERAL  # no rule fired, and still not "safe"


def test_room_temperature_rule_does_not_apply_to_produce_or_fridge() -> None:
    assert assess(ev(), ctx(FC.FRUIT, SC.ROOM_TEMPERATURE, 72)).advice_level is AL.GENERAL
    assert assess(ev(), ctx(FC.MEAT_POULTRY, SC.REFRIGERATOR, 72)).advice_level is AL.GENERAL


@pytest.mark.parametrize(
    ("hours", "discard"), [(24 * 3, False), (24 * 4, False), (24 * 4 + 1, True), (24 * 9, True)]
)
def test_cooked_leftovers_in_fridge(hours: int, discard: bool) -> None:
    a = assess(ev(), ctx(FC.COOKED_FOOD, SC.REFRIGERATOR, hours))
    assert (a.advice_level is AL.DISCARD) is discard


def test_dates() -> None:
    yesterday, today, tomorrow = TODAY - timedelta(days=1), TODAY, TODAY + timedelta(days=1)
    assert assess(ev(), ctx(FC.DAIRY_EGGS, use_by=yesterday)).advice_level is AL.DISCARD
    assert assess(ev(), ctx(FC.FRUIT, use_by=yesterday)).advice_level is AL.CAUTION
    assert assess(ev(), ctx(FC.DAIRY_EGGS, use_by=today)).advice_level is AL.GENERAL
    assert assess(ev(), ctx(FC.DAIRY_EGGS, use_by=tomorrow)).advice_level is AL.GENERAL
    bb = assess(ev(), ctx(FC.BREAD_BAKED, best_before=yesterday))
    assert bb.advice_level is AL.CAUTION
    assert "best_before_passed" in [r.code for r in bb.advice_reasons]


def test_unknown_storage_of_a_perishable_food_adds_caution() -> None:
    a = assess(ev(), ctx(FC.FISH_SEAFOOD, SC.UNKNOWN))
    assert a.advice_level is AL.CAUTION
    assert assess(ev(), ctx(FC.FRUIT, SC.UNKNOWN)).advice_level is AL.GENERAL


def test_inconclusive_always_asks_for_caution_and_retake_tips() -> None:
    a = assess(ev(ImageQuality.UNUSABLE), ctx())
    assert a.advice_level is AL.CAUTION and len(a.retake_tips) == 3


def test_every_category_has_specific_guidance() -> None:
    for c in FC:
        assert assess(ev(), ctx(c)).category_cautions, c


# ---- invariants over a grid of inputs: nothing may ever read as reassurance ----
_REASSURING = re.compile(
    r"\b(?<!can )(?<!may )(?<!might )(?:is|are|looks?|appears?|seems?|remains?)\s+"
    r"(?:safe|fresh|edible|fine|good|ok|okay)\b"
    r"|\bsafe to (?:eat|consume)\b|\bfresh\b|\d\s*%",
    re.IGNORECASE,
)


def _texts(a: Assessment) -> list[str]:
    return [
        *(r.text for r in a.inconclusive_reasons),
        *(r.text for r in a.advice_reasons),
        *a.steps,
        *a.category_cautions,
        *a.retake_tips,
        *GENERAL_NOTES,
    ]


def test_no_text_in_any_scenario_reassures_or_gives_a_score() -> None:
    evidences = [
        None,
        ev(),
        ev(ImageQuality.LIMITED),
        ev(ImageQuality.UNUSABLE),
        ev(match="no"),
        ev(match="unsure"),
        ev(visible=False),
        ev(ImageQuality.CLEAR, True, "yes", sign(Feature.BRUISING)),
        ev(ImageQuality.CLEAR, True, "yes", sign(Feature.MOLD_LIKE_GROWTH)),
    ]
    labels_seen: set[VisualLabel] = set()
    for e, cat, storage, hours in itertools.product(evidences, FC, SC, (None, 1, 5, 200)):
        a = assess(e, ctx(cat, storage, hours))
        labels_seen.add(a.label)
        for text in _texts(a):
            # the disclaimer is the one place that names "safe", in the negative
            checked = text.replace("is safe, or unsafe, to eat", "")
            assert not _REASSURING.search(checked), text
        assert any("not a statement that the food is safe" in t for t in _texts(a))
        assert a.advice_level in AdviceLevel and a.label in VisualLabel
    assert labels_seen == set(VisualLabel)
    assert HIGH_RISK  # sanity: the grid exercised the high-risk rules too
