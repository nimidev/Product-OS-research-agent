"""Tests for integration framework: adapter interface and registry (US-017)."""

from __future__ import annotations

import pytest

from research_agent.integrations import (
    IntegrationAdapter,
    IntegrationAdapterRegistry,
    PrepareSyncResponse,
    TestConnectionResponse,
    get_integration_registry,
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
