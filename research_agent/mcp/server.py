"""MCP server for Cursor — exposes search_memories and list_sources tools."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from research_agent.config.loader import get_settings
from research_agent.embedding.openai_provider import OpenAIEmbeddingProvider
from research_agent.memory.memory_service import MemoryService
from research_agent.storage.db import Database
from research_agent.storage.models import EntityType, SourceSystem
from research_agent.synthesis.summarizer import Summarizer
from research_agent.vector.qdrant_client import QdrantStore

logger = logging.getLogger(__name__)

mcp_app = Server("research-agent")

_memory_service: MemoryService | None = None


async def _get_memory_service() -> MemoryService:
    global _memory_service
    if _memory_service is not None:
        return _memory_service

    settings = get_settings()
    db = Database(db_path=settings.database_path)
    await db.init()

    vector_store = QdrantStore(host=settings.qdrant_host, port=settings.qdrant_port)
    embedding = OpenAIEmbeddingProvider(
        api_key=settings.openai_api_key, model=settings.embedding_model
    )
    await vector_store.ensure_collection(embedding.dimension())

    summarizer = (
        Summarizer(api_key=settings.openai_api_key, model=settings.llm_model)
        if settings.openai_api_key
        else None
    )

    _memory_service = MemoryService(
        db=db,
        vector_store=vector_store,
        embedding_provider=embedding,
        summarizer=summarizer,
    )
    return _memory_service


@mcp_app.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="search_memories",
            description=(
                "Search organizational knowledge base (feature requests, bugs, roadmap items, "
                "meeting notes, PRDs, support tickets). Returns AI-synthesized summary with "
                "source citations plus raw results for deeper analysis."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Natural language research question",
                    },
                    "filters": {
                        "type": "object",
                        "description": "Optional filters",
                        "properties": {
                            "source": {
                                "type": "string",
                                "enum": [s.value for s in SourceSystem],
                                "description": "Filter by data source",
                            },
                            "entity_types": {
                                "type": "array",
                                "items": {"type": "string", "enum": [t.value for t in EntityType]},
                                "description": "Filter by entity type(s). Omit for flexible search (inferred from query).",
                            },
                            "field_names": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Filter by field name(s), e.g. transcript, description.",
                            },
                            "date_from": {"type": "string", "description": "ISO date string for start of range"},
                            "date_to": {"type": "string", "description": "ISO date string for end of range"},
                            "tags": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Filter by tags",
                            },
                        },
                    },
                    "top_k": {
                        "type": "integer",
                        "description": "Number of results (default 10, max 50)",
                        "default": 10,
                    },
                    "context": {
                        "type": "string",
                        "description": (
                            "Previous conversation context for follow-up questions. "
                            "Include prior findings to refine the search."
                        ),
                    },
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="list_sources",
            description="List available data sources in the knowledge base.",
            inputSchema={
                "type": "object",
                "properties": {},
            },
        ),
    ]


@mcp_app.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    if name == "search_memories":
        return await _handle_search(arguments)
    elif name == "list_sources":
        return await _handle_list_sources()
    else:
        return [TextContent(type="text", text=f"Unknown tool: {name}")]


async def _handle_search(arguments: dict[str, Any]) -> list[TextContent]:
    query = arguments.get("query", "")
    if not query:
        return [TextContent(type="text", text="Error: query is required")]

    filters = arguments.get("filters", {})
    entity_types = arguments.get("entity_types") or filters.get("entity_types")
    field_names = arguments.get("field_names") or filters.get("field_names")
    top_k = min(arguments.get("top_k", 10), 50)
    context = arguments.get("context")

    svc = await _get_memory_service()
    result = await svc.search_memories(
        query=query,
        top_k=top_k,
        entity_types=entity_types,
        field_names=field_names,
        source=filters.get("source"),
        date_from=filters.get("date_from"),
        date_to=filters.get("date_to"),
        tags=filters.get("tags"),
        context=context,
    )

    response = {
        "summary": result.summary,
        "references": result.references,
        "raw_results": result.raw_results,
        "degraded": result.degraded,
    }
    return [TextContent(type="text", text=json.dumps(response, indent=2, default=str))]


async def _handle_list_sources() -> list[TextContent]:
    response = {
        "sources": [s.value for s in SourceSystem],
        "entity_types": [t.value for t in EntityType],
    }
    return [TextContent(type="text", text=json.dumps(response, indent=2))]


async def main() -> None:
    """Run the MCP server via stdio transport."""
    async with stdio_server() as (read_stream, write_stream):
        await mcp_app.run(read_stream, write_stream, mcp_app.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
