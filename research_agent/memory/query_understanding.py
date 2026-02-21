"""Simple query understanding: infer entity_types (and optionally field_names) from query + context.

When inference cannot determine scope, returns empty lists (search all).
"""

from __future__ import annotations

import re
from typing import Any

# Keywords that suggest narrowing to specific entity types (lowercase)
ENTITY_HINTS: dict[str, list[str]] = {
    "bug": ["bug", "bugs", "defect", "defects", "issue", "issues", "broken", "malfunction"],
    "feature_request": [
        "feature request", "feature requests", "feature request", "fr ", " pain point",
        "pain points", "ask for", "would like to have",
    ],
    "meeting_note": [
        "meeting", "meetings", "standup", "standups", "transcript", "transcripts",
        "discussion", "discussed", "said in the meeting", "notes from",
    ],
    "roadmap_item": ["roadmap", "roadmap item", "planned", "planning", "quarter", "timeline"],
    "prd": ["prd", "prds", "product spec", "specification", "requirements doc"],
    "support_ticket": [
        "support ticket", "ticket", "tickets", "customer complaint", "escalation",
    ],
}


def infer_entity_scope(query: str, context: str | None = None) -> tuple[list[str], list[str]]:
    """Infer entity_types (and optionally field_names) from query and optional context.

    Returns (entity_types, field_names). Empty lists mean no filter (search all).
    """
    text = (query or "").lower()
    if context:
        text = (context + " " + query).lower()

    entity_types: list[str] = []
    for entity_type, keywords in ENTITY_HINTS.items():
        if any(kw in text for kw in keywords):
            entity_types.append(entity_type)

    # Optional: infer field_names for very specific queries (e.g. "in the transcript" -> transcript)
    field_names: list[str] = []
    if "transcript" in text or "in the meeting" in text:
        field_names.append("transcript")
    if "description" in text and "in the description" in text:
        field_names.append("description")
    if "overview" in text or "prd overview" in text:
        field_names.append("overview")

    # Deduplicate and return; empty means search all
    return (list(dict.fromkeys(entity_types)), list(dict.fromkeys(field_names)))
