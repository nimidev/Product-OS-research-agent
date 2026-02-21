"""Load field mappings from YAML — source column → canonical entity field."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from research_agent.storage.models import EntityType

MAPPINGS_PATH = Path(__file__).resolve().parent.parent.parent / "config" / "mappings.yaml"
MAPPINGS_EXAMPLE_PATH = Path(__file__).resolve().parent.parent.parent / "config" / "mappings.example.yaml"


def load_mappings(path: Path | None = None) -> dict[str, Any]:
    """Load mappings YAML. Returns structure: source -> entity_type -> config with field_mappings."""
    p = path or MAPPINGS_PATH
    if not p.exists():
        p = MAPPINGS_EXAMPLE_PATH
    if not p.exists():
        return {}
    with open(p) as f:
        raw = yaml.safe_load(f) or {}
    return raw


def get_field_mapping(
    source: str,
    entity_type: str | EntityType,
    mappings: dict[str, Any] | None = None,
) -> dict[str, str]:
    """
    Get field_mappings for a source + entity_type.
    Returns dict: source_column_id -> canonical_field_name.
    """
    if mappings is None:
        mappings = load_mappings()
    entity_key = entity_type.value if isinstance(entity_type, EntityType) else entity_type
    source_config = mappings.get(source, {})
    entity_config = source_config.get(entity_key, {})
    return dict(entity_config.get("field_mappings", {}))


def get_connector_config(
    source: str,
    entity_type: str | EntityType,
    mappings: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Get full connector config (board_id, database_id, entity_type, field_mappings) for source + entity_type."""
    if mappings is None:
        mappings = load_mappings()
    entity_key = entity_type.value if isinstance(entity_type, EntityType) else entity_type
    source_config = mappings.get(source, {})
    return source_config.get(entity_key)
