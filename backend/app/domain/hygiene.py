"""Deterministic hygiene rules.

The model reports visible indicators. This module decides the report structure: fixed
suggested corrective actions, fixed disclosures about what photos cannot establish, fixed
not-assessable items, and severity summaries. No model text influences any of it.
"""

import enum

class LocationType(enum.StrEnum):
    RESTAURANT_KITCHEN = "restaurant_kitchen"
    CAFE = "cafe"
    FOOD_TRUCK = "food_truck"
    HOME_KITCHEN = "home_kitchen"
    INSTITUTIONAL = "institutional"
    OTHER = "other"

LOCATION_TYPE_LABELS: dict[LocationType, str] = {
    LocationType.RESTAURANT_KITCHEN: "Restaurant kitchen",
    LocationType.CAFE: "Café",
    LocationType.FOOD_TRUCK: "Food truck",
    LocationType.HOME_KITCHEN: "Home kitchen",
    LocationType.INSTITUTIONAL: "Institutional / commercial kitchen",
    LocationType.OTHER: "Other food area",
}

class FindingCategory(enum.StrEnum):
    SURFACE_CLEANLINESS = "surface_cleanliness"
    UNCOVERED_FOOD = "uncovered_food"
    RAW_READY_TO_EAT_SEPARATION = "raw_ready_to_eat_separation"
    WASTE_MANAGEMENT = "waste_management"
    TOOL_CLEANLINESS = "tool_cleanliness"
    OTHER_VISIBLE_CONCERN = "other_visible_concern"

CATEGORY_LABELS: dict[FindingCategory, str] = {
    FindingCategory.SURFACE_CLEANLINESS: "Surface cleanliness",
    FindingCategory.UNCOVERED_FOOD: "Uncovered food",
    FindingCategory.RAW_READY_TO_EAT_SEPARATION: "Raw / ready-to-eat separation",
    FindingCategory.WASTE_MANAGEMENT: "Waste management",
    FindingCategory.TOOL_CLEANLINESS: "Tool cleanliness",
    FindingCategory.OTHER_VISIBLE_CONCERN: "Other visible concern",
}

CATEGORY_ACTIONS: dict[FindingCategory, str] = {
    FindingCategory.SURFACE_CLEANLINESS: "Clean and sanitize the affected surface before preparing food.",
    FindingCategory.UNCOVERED_FOOD: "Cover or wrap the food, or store it in a sealed container.",
    FindingCategory.RAW_READY_TO_EAT_SEPARATION: "Store raw foods below ready-to-eat foods and use separate boards and utensils.",
    FindingCategory.WASTE_MANAGEMENT: "Empty bins, keep lids closed, and locate waste away from food preparation areas.",
    FindingCategory.TOOL_CLEANLINESS: "Wash and sanitize the affected tools before use.",
    FindingCategory.OTHER_VISIBLE_CONCERN: "Review the area and take an appropriate corrective action.",
}

class Severity(enum.StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"

SEVERITY_LABELS: dict[Severity, str] = {
    Severity.LOW: "Low",
    Severity.MEDIUM: "Medium",
    Severity.HIGH: "High",
}
SEVERITY_PRIORITY: dict[Severity, int] = {
    Severity.LOW: 1, Severity.MEDIUM: 2, Severity.HIGH: 3,
}

class Certainty(enum.StrEnum):
    CLEARLY_VISIBLE = "clearly_visible"
    POSSIBLY_VISIBLE = "possibly_visible"

CERTAINTY_LABELS: dict[Certainty, str] = {
    Certainty.CLEARLY_VISIBLE: "Clearly visible",
    Certainty.POSSIBLY_VISIBLE: "Possibly visible",
}

class InspectionStatus(enum.StrEnum):
    DRAFT = "draft"
    IN_REVIEW = "in_review"
    APPROVED = "approved"
    REJECTED = "rejected"

STATUS_LABELS: dict[InspectionStatus, str] = {
    InspectionStatus.DRAFT: "Draft",
    InspectionStatus.IN_REVIEW: "In review",
    InspectionStatus.APPROVED: "Approved",
    InspectionStatus.REJECTED: "Rejected",
}

# Every report carries these. They state what an ordinary photo cannot establish.
DISCLOSURES: tuple[str, ...] = (
    "This report describes only what is visible in the supplied photos. It cannot confirm the "
    "absence of pathogens, contamination, or pests.",
    "This report does not verify compliance with any law, regulation, or food-safety standard, "
    "and it is not an official inspection.",
    "This report does not include measured temperatures, microbial testing, or pest inspections.",
    "This report is not a substitute for an inspection by a qualified authority or for following "
    "the food-safety requirements that apply where this kitchen operates.",
    "The app does not perform face recognition or staff-performance surveillance. Findings relate "
    "only to visible conditions in the photographs.",
)

NOT_ASSESSABLE: tuple[str, ...] = (
    "Pathogen presence (bacteria, viruses, parasites) cannot be established from a photo.",
    "Food temperatures (refrigeration, cooking, holding) cannot be measured from a photo.",
    "Compliance with laws, regulations, or inspection standards cannot be confirmed from a photo.",
    "Areas not photographed are not covered; full-facility hygiene cannot be confirmed.",
    "Staff health, training, and personal hygiene practices cannot be judged from a photo.",
    "Pest activity beyond what is directly visible cannot be established from a photo.",
    "Water quality and plumbing conditions cannot be established from a photo.",
)

DEFAULT_CHECKLIST: tuple[dict[str, str], ...] = (
    {"item_id": "handwashing", "label": "Handwashing station is accessible and stocked (soap, water, towels)"},
    {"item_id": "food_protected", "label": "All food is covered or stored in sealed containers"},
    {"item_id": "raw_rte_separated", "label": "Raw and ready-to-eat foods are physically separated"},
    {"item_id": "surfaces_clean", "label": "Work surfaces are clean and sanitized"},
    {"item_id": "tools_clean", "label": "Utensils, boards, and containers are clean"},
    {"item_id": "waste_contained", "label": "Waste bins are closed and located away from prep areas"},
    {"item_id": "pest_evidence_absent", "label": "No visible signs of pests"},
    {"item_id": "temperatures_verified", "label": "Fridge and freezer temperatures were checked separately"},
)

def highest_severity(severities: list[str]) -> str | None:
    present = [Severity(s) for s in severities if s in Severity._value2member_map_]
    if not present:
        return None
    return max(present, key=lambda s: SEVERITY_PRIORITY[s]).value