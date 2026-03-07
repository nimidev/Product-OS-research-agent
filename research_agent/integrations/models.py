"""Unified config and mapping models for all integrations (US-017)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class EntityMappingConfig(BaseModel):
    """
    Per-entity mapping config; shared shape across integrations.

    Source-specific fields (e.g. board_ids, project_key, issue_type_names)
    go in source_payload so one model works for Monday, Jira, and future providers.
    """

    entity_type: str
    field_mappings: dict[str, str] = Field(default_factory=dict)
    direction: str = "source_to_os"  # two_way | source_to_os | monday_to_os | jira_to_os
    source_payload: dict[str, Any] = Field(default_factory=dict)


class IntegrationConfigRequest(BaseModel):
    """
    Request body for upserting integration config; shared across integrations.

    Credentials and source-specific fields (board_ids, cloud_id, subdomain, etc.)
    go in source_payload so one shape works for all.
    """

    enabled: bool = True
    entity_mappings: dict[str, str] = Field(default_factory=dict)
    entity_configs: dict[str, EntityMappingConfig] = Field(default_factory=dict)
    sync_interval_seconds: int = Field(default=7200, ge=300, le=86400)
    source_payload: dict[str, Any] = Field(default_factory=dict)


class IntegrationConfigResponse(BaseModel):
    """
    Response shape for get_config; shared across integrations.

    No raw credentials; use credentials_set (and optional flags in source_payload).
    Source-specific fields (board_ids, subdomain, cloud_id, site_url, etc.) in source_payload.
    """

    source: str
    enabled: bool
    credentials_set: bool = False
    entity_mappings: dict[str, str] = Field(default_factory=dict)
    entity_configs: dict[str, EntityMappingConfig] = Field(default_factory=dict)
    sync_interval_seconds: int = 7200
    updated_at: str | None = None
    source_payload: dict[str, Any] = Field(default_factory=dict)


def entity_config_from_dict(data: dict[str, Any]) -> EntityMappingConfig:
    """Build EntityMappingConfig from a stored entity_config dict (e.g. from DB JSON)."""
    common = ("entity_type", "field_mappings", "direction")
    source_payload = {k: v for k, v in data.items() if k not in common}
    return EntityMappingConfig(
        entity_type=data.get("entity_type", ""),
        field_mappings=dict(data.get("field_mappings", {})),
        direction=data.get("direction", "source_to_os"),
        source_payload=source_payload,
    )


def entity_config_to_dict(config: EntityMappingConfig) -> dict[str, Any]:
    """Serialize EntityMappingConfig to a dict for DB storage (JSON)."""
    out: dict[str, Any] = {
        "entity_type": config.entity_type,
        "field_mappings": config.field_mappings,
        "direction": config.direction,
    }
    out.update(config.source_payload)
    return out


# Keys that are part of the common response shape (not source_payload).
_COMMON_RESPONSE_KEYS = frozenset(
    {
        "source",
        "enabled",
        "entity_mappings",
        "entity_configs",
        "sync_interval_seconds",
        "updated_at",
    }
)
# Keys that indicate credentials are set (per source convention).
_CREDENTIALS_KEYS: dict[str, list[str]] = {
    "monday": ["api_key"],
    "jira": ["access_token"],  # Jira may store token in a different key; adapter can override.
}


def response_from_db_dict(source: str, db_dict: dict[str, Any]) -> IntegrationConfigResponse:
    """
    Build IntegrationConfigResponse from the dict returned by Database.get_integration_config.

    Common keys are mapped; the rest go into source_payload. credentials_set is derived
    from source-specific credential keys (api_key for monday, etc.).
    """
    entity_configs = {
        k: entity_config_from_dict(v) if isinstance(v, dict) else v
        for k, v in (db_dict.get("entity_configs") or {}).items()
    }
    source_payload = {
        k: v for k, v in db_dict.items() if k not in _COMMON_RESPONSE_KEYS and k != "entity_configs"
    }
    # Normalize entity_configs values that are already EntityMappingConfig
    entity_configs_out: dict[str, EntityMappingConfig] = {}
    for k, v in entity_configs.items():
        if isinstance(v, EntityMappingConfig):
            entity_configs_out[k] = v
        elif isinstance(v, dict):
            entity_configs_out[k] = entity_config_from_dict(v)
        else:
            continue

    cred_keys = _CREDENTIALS_KEYS.get(source, ["api_key"])

    def _has_value(k: str) -> bool:
        v = db_dict.get(k)
        if not v:
            return False
        return str(v).strip() != "" if isinstance(v, str) else True

    credentials_set = any(_has_value(k) for k in cred_keys)
    # For Jira, access_token may be stored under a different key; check common patterns.
    if source == "jira" and not credentials_set:
        credentials_set = bool(db_dict.get("api_key"))  # some stores reuse api_key for token

    updated_at = db_dict.get("updated_at")
    if hasattr(updated_at, "isoformat"):
        updated_at = updated_at.isoformat()  # type: ignore[union-attr]

    return IntegrationConfigResponse(
        source=source,
        enabled=bool(db_dict.get("enabled", False)),
        credentials_set=credentials_set,
        entity_mappings=dict(db_dict.get("entity_mappings") or {}),
        entity_configs=entity_configs_out,
        sync_interval_seconds=int(db_dict.get("sync_interval_seconds", 7200)),
        updated_at=updated_at,
        source_payload=source_payload,
    )
