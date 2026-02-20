"""Tests for FastAPI REST API endpoints."""

from __future__ import annotations

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
                    "type": "bug",
                    "metadata": {},
                    "created_at": "2025-06-15T00:00:00+00:00",
                }
            ],
            degraded=False,
        )
    )
    return svc


@pytest.fixture
async def client(mock_memory_service):
    import research_agent.api.server as api_module

    api_module._memory_service = mock_memory_service
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    api_module._memory_service = None


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
                "filters": {"source": "mock", "type": "bug"},
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
