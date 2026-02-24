from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from research_agent.__main__ import _build_connectors


@pytest.mark.asyncio
async def test_build_connectors_prefers_monday_integration_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("MONDAY_API_KEY", raising=False)

    db = AsyncMock()
    db.get_integration_config = AsyncMock(
        return_value={
            "enabled": True,
            "api_key": "db-token",
            "board_ids": ["123", "456"],
            "entity_mappings": {
                "123": "feature_request",
                "456": "bug",
            },
            "sync_interval_seconds": 7200,
        }
    )

    monkeypatch.setattr(
        "research_agent.config.mappings.load_mappings",
        lambda: {
            "monday": {
                "feature_request": {
                    "entity_type": "feature_request",
                    "field_mappings": {"name": "title", "text0": "description"},
                },
                "bug": {
                    "entity_type": "bug",
                    "field_mappings": {"name": "title", "text0": "description"},
                },
            },
            "notion": {},
        },
    )

    connectors = await _build_connectors(db)
    monday_connectors = [c for c in connectors if c.source_name == "monday"]
    assert len(monday_connectors) == 2
    assert {c.entity_type for c in monday_connectors} == {"feature_request", "bug"}


@pytest.mark.asyncio
async def test_build_connectors_falls_back_to_yaml_and_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MONDAY_API_KEY", "env-token")

    db = AsyncMock()
    db.get_integration_config = AsyncMock(return_value=None)

    monkeypatch.setattr(
        "research_agent.config.mappings.load_mappings",
        lambda: {
            "monday": {
                "feature_request": {
                    "board_id": "999",
                    "entity_type": "feature_request",
                    "field_mappings": {"name": "title"},
                }
            },
            "notion": {},
        },
    )

    connectors = await _build_connectors(db)
    monday_connectors = [c for c in connectors if c.source_name == "monday"]
    assert len(monday_connectors) == 1
    assert monday_connectors[0].entity_type == "feature_request"
