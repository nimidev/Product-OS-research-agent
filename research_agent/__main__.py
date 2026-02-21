"""CLI entry point: python -m research_agent <command>."""

from __future__ import annotations

import sys


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python -m research_agent <command>")
        print("Commands: seed, serve, mcp, sync")
        sys.exit(1)

    command = sys.argv[1]

    if command == "seed":
        from research_agent.seed import main as seed_main
        seed_main()
    elif command == "serve":
        import uvicorn
        uvicorn.run(
            "research_agent.api.server:app",
            host="0.0.0.0",
            port=8000,
            reload=False,
        )
    elif command == "mcp":
        import asyncio
        from research_agent.mcp.server import main as mcp_main
        asyncio.run(mcp_main())
    elif command == "sync":
        import asyncio
        asyncio.run(_run_sync())
    else:
        print(f"Unknown command: {command}")
        print("Commands: seed, serve, mcp, sync")
        sys.exit(1)


async def _run_sync() -> None:
    """Run sync with all configured connectors (from config/mappings.yaml)."""
    import logging
    import os

    from research_agent.config.loader import get_settings
    from research_agent.config.mappings import load_mappings
    from research_agent.connectors.monday_connector import MondayConnector
    from research_agent.connectors.notion_connector import NotionConnector
    from research_agent.embedding.openai_provider import OpenAIEmbeddingProvider
    from research_agent.logging_config import configure_logging
    from research_agent.storage.db import Database
    from research_agent.sync.sync_all import SyncEngine
    from research_agent.vector.qdrant_client import QdrantStore

    settings = get_settings()
    configure_logging(settings.log_level)
    logger = logging.getLogger(__name__)

    db = Database(db_path=settings.database_path)
    await db.init()

    vector_store = QdrantStore(host=settings.qdrant_host, port=settings.qdrant_port)
    embedder = OpenAIEmbeddingProvider(
        api_key=settings.openai_api_key, model=settings.embedding_model
    )
    await vector_store.ensure_collection(embedder.dimension())

    connectors = _build_connectors_from_mappings()
    logger.info("Starting sync with %d connectors", len(connectors))

    engine = SyncEngine(
        db=db,
        vector_store=vector_store,
        embedding_provider=embedder,
        connectors=connectors,
    )
    result = await engine.sync_all()
    logger.info("Sync result: %s", result)

    await vector_store.close()
    await db.close()


def _build_connectors_from_mappings() -> list:
    """Build connector instances from config/mappings.yaml (and env API keys)."""
    import os

    from research_agent.connectors.base import BaseConnector
    from research_agent.connectors.monday_connector import MondayConnector
    from research_agent.connectors.notion_connector import NotionConnector

    connectors: list[BaseConnector] = []
    mappings = load_mappings()
    if not mappings:
        return connectors

    monday_key = os.environ.get("MONDAY_API_KEY", "")
    for entity_key, cfg in mappings.get("monday", {}).items():
        if not isinstance(cfg, dict) or not monday_key:
            continue
        board_id = cfg.get("board_id")
        entity_type = cfg.get("entity_type", entity_key)
        field_mappings = cfg.get("field_mappings", {})
        if board_id and field_mappings:
            connectors.append(
                MondayConnector(
                    api_key=monday_key,
                    board_id=str(board_id),
                    entity_type=entity_type,
                    field_mappings=field_mappings,
                )
            )

    notion_key = os.environ.get("NOTION_API_KEY", "")
    for entity_key, cfg in mappings.get("notion", {}).items():
        if not isinstance(cfg, dict) or not notion_key:
            continue
        database_id = cfg.get("database_id")
        entity_type = cfg.get("entity_type", entity_key)
        field_mappings = cfg.get("field_mappings", {})
        if database_id and field_mappings:
            connectors.append(
                NotionConnector(
                    api_key=notion_key,
                    database_id=str(database_id),
                    entity_type=entity_type,
                    field_mappings=field_mappings,
                )
            )

    return connectors


if __name__ == "__main__":
    main()
