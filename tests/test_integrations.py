"""Tests for integration framework: adapter interface, registry, and models (US-017)."""

from __future__ import annotations

from datetime import UTC, datetime

from research_agent.integrations import (
    EntityMappingConfig,
    IntegrationAdapter,
    IntegrationAdapterRegistry,
    IntegrationConfigRequest,
    PrepareSyncResponse,
    TestConnectionResponse,
    entity_config_from_dict,
    entity_config_to_dict,
    get_integration_registry,
    response_from_db_dict,
)


def test_test_connection_response_model() -> None:
    r = TestConnectionResponse(ok=True, detail="Connected")
    assert r.ok is True
    assert r.detail == "Connected"
    r2 = TestConnectionResponse(ok=False)
    assert r2.detail == ""


def test_prepare_sync_response_model() -> None:
    r = PrepareSyncResponse(ok=True, fetched=10, embedded=10, errors=0)
    assert r.ok is True
    assert r.fetched == 10
    assert r.embedded == 10
    assert r.total_entities == 0


class _StubAdapter(IntegrationAdapter):
    """Minimal adapter impl for tests."""

    def __init__(self, source_id: str, auth_type: str = "api_key") -> None:
        self._source_id = source_id
        self._auth_type = auth_type

    @property
    def source_id(self) -> str:
        return self._source_id

    @property
    def auth_type(self) -> str:
        return self._auth_type

    async def get_config(self, db: object) -> dict:
        return {}

    async def upsert_config(self, db: object, request: dict) -> dict:
        return {}

    async def get_schema(self, db: object) -> dict:
        return {}

    async def test_connection(self, db: object) -> TestConnectionResponse:
        return TestConnectionResponse(ok=True)

    async def prepare_sync(self, db: object) -> PrepareSyncResponse:
        return PrepareSyncResponse(ok=True)


def test_registry_register_get_list() -> None:
    registry = IntegrationAdapterRegistry()
    assert registry.get("monday") is None
    assert registry.list_integrations() == []

    stub = _StubAdapter("monday", "api_key")
    registry.register("monday", stub)
    assert registry.get("monday") is stub
    assert registry.list_integrations() == [{"source_id": "monday", "auth_type": "api_key"}]
    assert registry.source_ids() == ["monday"]


def test_registry_register_with_explicit_auth_type() -> None:
    registry = IntegrationAdapterRegistry()
    stub = _StubAdapter("jira", "api_key")
    registry.register("jira", stub, auth_type="oauth")
    assert registry.list_integrations() == [{"source_id": "jira", "auth_type": "oauth"}]


def test_get_integration_registry_singleton() -> None:
    r1 = get_integration_registry()
    r2 = get_integration_registry()
    assert r1 is r2


# ---------------------------------------------------------------------------
# Unified config/mapping models
# ---------------------------------------------------------------------------


def test_entity_mapping_config_source_payload() -> None:
    c = EntityMappingConfig(
        entity_type="feature_request",
        field_mappings={"summary": "title"},
        direction="source_to_os",
        source_payload={"board_ids": ["123"], "project_key": "PROJ"},
    )
    assert c.entity_type == "feature_request"
    assert c.source_payload["board_ids"] == ["123"]
    d = entity_config_to_dict(c)
    assert d["entity_type"] == "feature_request"
    assert d["board_ids"] == ["123"]
    c2 = entity_config_from_dict(d)
    assert c2.entity_type == c.entity_type
    assert c2.source_payload.get("board_ids") == ["123"]


def test_response_from_db_dict_monday() -> None:
    db_dict = {
        "source": "monday",
        "enabled": True,
        "api_key": "secret",
        "board_ids": ["1", "2"],
        "entity_mappings": {"feature_request": "1"},
        "entity_configs": {
            "feature_request": {
                "entity_type": "feature_request",
                "field_mappings": {"name": "title"},
                "direction": "two_way",
                "board_ids": ["1"],
            },
        },
        "sync_interval_seconds": 3600,
        "subdomain": "my-team",
        "updated_at": datetime.now(UTC),
    }
    r = response_from_db_dict("monday", db_dict)
    assert r.source == "monday"
    assert r.enabled is True
    assert r.credentials_set is True
    assert r.entity_mappings == {"feature_request": "1"}
    assert "feature_request" in r.entity_configs
    assert r.entity_configs["feature_request"].field_mappings == {"name": "title"}
    assert r.source_payload.get("board_ids") == ["1", "2"]
    assert r.source_payload.get("subdomain") == "my-team"


def test_integration_config_request_response_roundtrip() -> None:
    req = IntegrationConfigRequest(
        enabled=True,
        entity_mappings={"bug": "2"},
        entity_configs={
            "bug": EntityMappingConfig(
                entity_type="bug",
                field_mappings={"summary": "title"},
                source_payload={"project_key": "PROJ"},
            ),
        },
        sync_interval_seconds=7200,
        source_payload={"board_ids": ["1"]},
    )
    assert req.enabled is True
    assert req.entity_configs["bug"].source_payload["project_key"] == "PROJ"
