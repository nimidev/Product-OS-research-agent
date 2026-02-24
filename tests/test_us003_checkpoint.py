"""US-003 checkpoint tests: verify Monday search via API and MCP before chat UI."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from research_agent.api.server import app
from research_agent.mcp.server import call_tool
from research_agent.memory.memory_service import MemorySearchResult


@pytest.fixture
def monday_memory_result() -> MemorySearchResult:
    return MemorySearchResult(
        summary="Monday checkpoint summary",
        references=[
            {
                "title": "Monday Item 1",
                "url": "https://monday.com/boards/123/pulses/1",
                "source": "monday",
                "type": "feature_request",
            }
        ],
        raw_results=[
            {
                "id": "monday:1",
                "score": 0.99,
                "title": "Improve onboarding flow",
                "body": "Customer pain points around onboarding time",
                "source": "monday",
                "entity_type": "feature_request",
                "field_name": "description",
                "metadata": {"board_id": "123"},
                "created_at": "2026-02-23T00:00:00+00:00",
            }
        ],
        degraded=False,
    )


@pytest.fixture
def mock_memory_service(monday_memory_result: MemorySearchResult) -> AsyncMock:
    svc = AsyncMock()
    svc.search_memories = AsyncMock(return_value=monday_memory_result)
    return svc


@pytest.fixture
def mock_db() -> AsyncMock:
    db = AsyncMock()
    db.get_integration_config = AsyncMock(return_value=None)
    return db


@pytest.mark.asyncio
async def test_checkpoint_api_sources_and_search(
    mock_memory_service: AsyncMock,
    mock_db: AsyncMock,
) -> None:
    import research_agent.api.server as api_module

    api_module._memory_service = mock_memory_service
    api_module._db = mock_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        sources_resp = await client.get("/sources")
        assert sources_resp.status_code == 200
        sources_data = sources_resp.json()
        assert "monday" in sources_data["sources"]

        search_resp = await client.post(
            "/search_memories",
            json={"query": "What are Monday onboarding pain points?"},
        )
        assert search_resp.status_code == 200
        search_data = search_resp.json()
        assert search_data["raw_results"][0]["source"] == "monday"
        assert search_data["references"][0]["source"] == "monday"
        assert "Monday checkpoint summary" in search_data["summary"]

    api_module._memory_service = None
    api_module._db = None


@pytest.mark.asyncio
async def test_checkpoint_mcp_tools_for_monday(mock_memory_service: AsyncMock) -> None:
    with patch(
        "research_agent.mcp.server._get_memory_service",
        new=AsyncMock(return_value=mock_memory_service),
    ):
        list_sources_result = await call_tool("list_sources", {})
        sources_payload = json.loads(list_sources_result[0].text)
        assert "monday" in sources_payload["sources"]

        search_result = await call_tool(
            "search_memories",
            {"query": "Show Monday feature requests about onboarding"},
        )
        search_payload = json.loads(search_result[0].text)
        assert search_payload["raw_results"][0]["source"] == "monday"
        assert search_payload["references"][0]["source"] == "monday"
