"""Tests for MCP server tool registration and responses."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from research_agent.mcp.server import call_tool, list_tools, _get_memory_service
from research_agent.memory.memory_service import MemorySearchResult


class TestToolListing:
    @pytest.mark.asyncio
    async def test_list_tools_returns_two(self):
        tools = await list_tools()
        assert len(tools) == 2
        names = {t.name for t in tools}
        assert "search_memories" in names
        assert "list_sources" in names

    @pytest.mark.asyncio
    async def test_search_tool_schema(self):
        tools = await list_tools()
        search_tool = next(t for t in tools if t.name == "search_memories")
        schema = search_tool.inputSchema
        assert "query" in schema["properties"]
        assert "query" in schema["required"]


class TestToolCalls:
    @pytest.mark.asyncio
    async def test_list_sources(self):
        results = await call_tool("list_sources", {})
        assert len(results) == 1
        data = json.loads(results[0].text)
        assert "mock" in data["sources"]
        assert "feature_request" in data["entity_types"]

    @pytest.mark.asyncio
    async def test_unknown_tool(self):
        results = await call_tool("nonexistent", {})
        assert "Unknown tool" in results[0].text

    @pytest.mark.asyncio
    async def test_search_empty_query(self):
        results = await call_tool("search_memories", {"query": ""})
        assert "Error" in results[0].text

    @pytest.mark.asyncio
    @patch("research_agent.mcp.server._get_memory_service")
    async def test_search_with_mock_service(self, mock_get_svc):
        mock_svc = AsyncMock()
        mock_svc.search_memories = AsyncMock(
            return_value=MemorySearchResult(
                summary="Found 3 relevant items.",
                references=[],
                raw_results=[{"id": "item1", "title": "Bug A", "score": 0.9}],
                degraded=False,
            )
        )
        mock_get_svc.return_value = mock_svc

        results = await call_tool("search_memories", {"query": "bugs in auth"})
        data = json.loads(results[0].text)
        assert "Found 3 relevant items" in data["summary"]
        assert len(data["raw_results"]) == 1
