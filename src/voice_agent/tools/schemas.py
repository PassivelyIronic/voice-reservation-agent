"""Tool definitions from docs/plan/05-tools-spec.md: the single source of LLM-facing schemas."""

from dataclasses import dataclass
from typing import Any

HANDOFF_REASONS = [
    "large_party",
    "allergen_unknown",
    "severe_allergy",
    "tool_failure",
    "customer_request",
    "complaint",
    "out_of_scope",
]


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    properties: dict[str, Any]
    required: list[str]


TOOL_SPECS: tuple[ToolSpec, ...] = (
    ToolSpec(
        name="get_restaurant_info",
        description=(
            "Get verified restaurant facts: opening hours, address, parking, policies. "
            "Use instead of answering from memory."
        ),
        properties={
            "topic": {
                "type": "string",
                "enum": [
                    "opening_hours",
                    "address",
                    "parking",
                    "large_groups",
                    "dress_code",
                    "accessibility",
                ],
            },
            "date": {
                "type": "string",
                "format": "date",
                "description": "Optional. For opening_hours on a specific date (YYYY-MM-DD).",
            },
        },
        required=["topic"],
    ),
    ToolSpec(
        name="check_availability",
        description=(
            "Check if a table is available and place a 5-minute hold on it. "
            "Always call before create_reservation. "
            "Resolve relative dates using today's date from the system prompt."
        ),
        properties={
            "date": {
                "type": "string",
                "format": "date",
                "description": "YYYY-MM-DD in restaurant local time",
            },
            "time": {
                "type": "string",
                "pattern": "^([01]\\d|2[0-3]):[0-5]\\d$",
                "description": "24h HH:MM",
            },
            "party_size": {"type": "integer", "minimum": 1, "maximum": 20},
            "zone_preference": {
                "type": "string",
                "enum": ["any", "window", "terrace", "main"],
                "default": "any",
            },
        },
        required=["date", "time", "party_size"],
    ),
    ToolSpec(
        name="create_reservation",
        description=(
            "Confirm a held table. Only call after reading the hold back to the customer "
            "and receiving an explicit yes in a later turn."
        ),
        properties={
            "hold_id": {"type": "string"},
            "customer_name": {"type": "string", "minLength": 1, "maxLength": 80},
            "phone": {"type": "string", "description": "Digits as spoken; server normalizes."},
            "notes": {
                "type": "string",
                "maxLength": 200,
                "description": "Only what the customer said, e.g. 'nut allergy'.",
            },
        },
        required=["hold_id", "customer_name", "phone"],
    ),
    ToolSpec(
        name="search_menu",
        description=(
            "Find menu items by name or description. Returns item ids needed by get_allergen_info."
        ),
        properties={
            "query": {"type": "string"},
            "category": {
                "type": "string",
                "enum": ["any", "starter", "pasta", "main", "dessert", "drink"],
                "default": "any",
            },
        },
        required=["query"],
    ),
    ToolSpec(
        name="get_allergen_info",
        description=(
            "The ONLY source for allergen answers. Never state allergen facts that are not "
            "in this tool's result. Speak 'spoken_answer' as given."
        ),
        properties={
            "item_id": {"type": "string"},
            "allergens": {
                "type": "array",
                "items": {"type": "string"},
                "minItems": 1,
                "description": (
                    "Allergens as the customer said them, e.g. ['nuts'] or ['dairy','gluten']"
                ),
            },
        },
        required=["item_id", "allergens"],
    ),
    ToolSpec(
        name="transfer_to_human",
        description=(
            "Hand the conversation to restaurant staff. Use for: party larger than 8, unknown or "
            "severe allergy questions the records cannot answer, complaints, explicit requests "
            "for a person, repeated tool failures, anything outside reservations/menu/hours."
        ),
        properties={
            "reason": {"type": "string", "enum": HANDOFF_REASONS},
            "summary": {
                "type": "string",
                "maxLength": 300,
                "description": "One-paragraph summary for staff.",
            },
        },
        required=["reason", "summary"],
    ),
)
