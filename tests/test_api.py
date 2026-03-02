"""Tests for FastAPI REST API endpoints."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from research_agent.api.server import app
from research_agent.memory.memory_service import MemorySearchResult


@pytest.fixture
def mock_memory_service():
    svc = AsyncMock()
    svc.search_memories = AsyncMock(
        return_value=MemorySearchResult(
            summary="Test summary about the query.",
            references=[
                {"title": "Item A", "url": "http://example.com/a", "source": "mock", "type": "bug"}
            ],
            raw_results=[
                {
                    "id": "item1",
                    "score": 0.95,
                    "title": "Item A",
                    "body": "Details",
                    "source": "mock",
                    "entity_type": "bug",
                    "field_name": "description",
                    "metadata": {},
                    "created_at": "2025-06-15T00:00:00+00:00",
                }
            ],
            degraded=False,
        )
    )
    return svc


@pytest.fixture
def mock_db():
    db = AsyncMock()
    db.get_integration_config = AsyncMock(return_value=None)
    db.upsert_integration_config = AsyncMock(
        return_value={
            "source": "monday",
            "enabled": True,
            "api_key": "token",
            "board_ids": ["123"],
            "entity_mappings": {"123": "feature_request"},
            "sync_interval_seconds": 7200,
            "updated_at": datetime.now(UTC),
        }
    )
    return db


@pytest.fixture
async def client(mock_memory_service, mock_db):
    import research_agent.api.server as api_module

    api_module._memory_service = mock_memory_service
    api_module._db = mock_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    api_module._memory_service = None
    api_module._db = None


class TestHealthEndpoint:
    @pytest.mark.asyncio
    async def test_health(self, client):
        resp = await client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}


class TestSourcesEndpoint:
    @pytest.mark.asyncio
    async def test_list_sources(self, client):
        resp = await client.get("/sources")
        assert resp.status_code == 200
        data = resp.json()
        assert "mock" in data["sources"]
        assert "monday" in data["sources"]
        assert "notion" in data["sources"]


class TestSearchEndpoint:
    @pytest.mark.asyncio
    async def test_search(self, client, mock_memory_service):
        resp = await client.post("/search_memories", json={"query": "bugs"})
        assert resp.status_code == 200
        data = resp.json()
        assert "summary" in data
        assert "references" in data
        assert "raw_results" in data
        mock_memory_service.search_memories.assert_called_once()

    @pytest.mark.asyncio
    async def test_search_with_filters(self, client, mock_memory_service):
        resp = await client.post(
            "/search_memories",
            json={
                "query": "performance",
                "filters": {"source": "mock", "entity_types": ["bug"]},
                "top_k": 5,
            },
        )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_search_empty_query(self, client):
        resp = await client.post("/search_memories", json={"query": ""})
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_search_with_context(self, client, mock_memory_service):
        resp = await client.post(
            "/search_memories",
            json={"query": "follow up", "context": "previous findings about auth"},
        )
        assert resp.status_code == 200


class TestMondayIntegrationConfigEndpoints:
    @pytest.mark.asyncio
    async def test_get_default_monday_config(self, client):
        resp = await client.get("/integrations/monday")
        assert resp.status_code == 200
        data = resp.json()
        assert data["source"] == "monday"
        assert data["enabled"] is False
        assert data["api_key_set"] is False
        assert data["sync_interval_seconds"] == 7200

    @pytest.mark.asyncio
    async def test_put_monday_config(self, client, mock_db):
        resp = await client.put(
            "/integrations/monday",
            json={
                "enabled": True,
                "api_key": "monday-token",
                "board_ids": ["123"],
                "entity_mappings": {"123": "feature_request"},
                "sync_interval_seconds": 7200,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["enabled"] is True
        assert data["api_key_set"] is True
        mock_db.upsert_integration_config.assert_called_once()

    @pytest.mark.asyncio
    async def test_test_monday_connection_requires_key(self, client):
        resp = await client.post("/integrations/monday/test", json={})
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_test_monday_connection_success(self, client):
        with patch(
            "research_agent.api.server.MondayConnector.health_check",
            new=AsyncMock(return_value=True),
        ):
            resp = await client.post(
                "/integrations/monday/test",
                json={"api_key": "monday-token"},
            )
        assert resp.status_code == 200
        assert resp.json()["ok"] is True


class TestMondaySchemaEndpoint:
    @pytest.mark.asyncio
    async def test_get_monday_schema_requires_key(self, client, mock_db):
        # No api_key in config -> 400
        mock_db.get_integration_config.return_value = {
            "enabled": True,
            "api_key": "",
            "board_ids": [],
            "entity_mappings": {},
            "entity_configs": {},
            "sync_interval_seconds": 7200,
            "updated_at": datetime.now(UTC),
        }
        resp = await client.get("/integrations/monday/schema")
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_get_monday_schema_happy_path(self, client, mock_db, monkeypatch):
        mock_db.get_integration_config.return_value = {
            "enabled": True,
            "api_key": "monday-token",
            "board_ids": [],
            "entity_mappings": {},
            "entity_configs": {},
            "sync_interval_seconds": 7200,
            "updated_at": datetime.now(UTC),
        }

        async def fake_fetch_schema(api_key: str):
            assert api_key == "monday-token"
            return [
                {
                    "id": "123",
                    "name": "Product Epics",
                    "columns": [
                        {"id": "name", "title": "Name", "type": "name"},
                        {"id": "status", "title": "Status", "type": "status"},
                    ],
                }
            ]

        monkeypatch.setattr(
            "research_agent.api.server._fetch_monday_boards_schema", fake_fetch_schema
        )

        resp = await client.get("/integrations/monday/schema")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["boards"]) == 1
        assert data["boards"][0]["id"] == "123"
        assert data["boards"][0]["name"] == "Product Epics"
