"""CLI entry point: python -m research_agent <command>."""

from __future__ import annotations

import sys


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python -m research_agent <command>")
        print("Commands: setup, serve, seed, sync, mcp, doctor")
        sys.exit(1)

    command = sys.argv[1]

    if command == "setup":
        from research_agent.setup import run_setup
        run_setup()
    elif command == "seed":
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
    elif command == "doctor":
        from research_agent.doctor import run_doctor
        run_doctor()
    else:
        print(f"Unknown command: {command}")
        print("Commands: setup, serve, seed, sync, mcp, doctor")
        sys.exit(1)


async def _run_sync() -> None:
    """Run sync with connectors from integration config + mappings.yaml fallback."""
    import logging

    from research_agent.config.loader import create_vector_store, get_settings
    from research_agent.embedding.openai_provider import OpenAIEmbeddingProvider
    from research_agent.logging_config import configure_logging
    from research_agent.storage.db import Database
    from research_agent.sync.sync_all import SyncEngine

    settings = get_settings()
    configure_logging(settings.log_level)
    logger = logging.getLogger(__name__)

    db = Database(db_path=settings.database_path)
    await db.init()

    vector_store = create_vector_store(settings)
    embedder = OpenAIEmbeddingProvider(
        api_key=settings.openai_api_key, model=settings.embedding_model
    )
    await vector_store.ensure_collection(embedder.dimension())

    connectors = await _build_connectors(db)
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


def _resolve_monday_field_mappings(entity_type: str, mappings: dict) -> dict[str, str]:
    monday_cfg = mappings.get("monday", {})
    # Prefer explicit entity_type match in mapping config.
    for entity_key, cfg in monday_cfg.items():
        if not isinstance(cfg, dict):
            continue
        mapped_type = str(cfg.get("entity_type", entity_key))
        if mapped_type == entity_type:
            field_mappings = cfg.get("field_mappings", {})
            if isinstance(field_mappings, dict) and field_mappings:
                return {str(k): str(v) for k, v in field_mappings.items()}

    # Safe fallback for minimal ingestion.
    return {"name": "title"}


async def _build_connectors(db) -> list:
    """Build connectors from DB integration config; fallback to mappings.yaml + env."""
    import os

    from research_agent.config.mappings import load_mappings
    from research_agent.connectors.base import BaseConnector
    from research_agent.connectors.monday_connector import MondayConnector
    from research_agent.connectors.notion_connector import NotionConnector

    connectors: list[BaseConnector] = []
    mappings = load_mappings()

    monday_cfg = await db.get_integration_config("monday")
    monday_added = False
    if monday_cfg and bool(monday_cfg.get("enabled")):
        monday_key = str(monday_cfg.get("api_key", "")).strip() or os.environ.get(
            "MONDAY_API_KEY", ""
        )
        entity_configs = dict(monday_cfg.get("entity_configs", {}))
        entity_mappings = {
            str(k): str(v) for k, v in dict(monday_cfg.get("entity_mappings", {})).items()
        }

        if entity_configs:
            # New path: use rich per-entity configs (board_ids + field_mappings + direction).
            for _, cfg in entity_configs.items():
                boards = [
                    str(b).strip()
                    for b in list(cfg.get("board_ids", []))
                    if str(b).strip()
                ]
                entity_type = str(cfg.get("entity_type") or "").strip()
                # Fall back to legacy mapping if entity_type not set but we can infer from board_ids.
                if not entity_type and boards and entity_mappings:
                    entity_type = entity_mappings.get(str(boards[0]), "")
                if not entity_type or not monday_key:
                    continue

                field_mappings = dict(cfg.get("field_mappings") or {})
                if not field_mappings:
                    field_mappings = _resolve_monday_field_mappings(entity_type, mappings)

                for board_id in boards:
                    connectors.append(
                        MondayConnector(
                            api_key=monday_key,
                            board_id=board_id,
                            entity_type=entity_type,
                            field_mappings=field_mappings,
                        )
                    )
                    monday_added = True
        else:
            # Legacy path: entity_mappings + board_ids from config.
            board_ids = [
                str(board_id).strip()
                for board_id in list(monday_cfg.get("board_ids", []))
                if str(board_id).strip()
            ]
            if not board_ids and entity_mappings:
                board_ids = list(entity_mappings.keys())

            for board_id in board_ids:
                entity_type = entity_mappings.get(str(board_id))
                if not entity_type or not monday_key:
                    continue
                field_mappings = _resolve_monday_field_mappings(entity_type, mappings)
                connectors.append(
                    MondayConnector(
                        api_key=monday_key,
                        board_id=board_id,
                        entity_type=entity_type,
                        field_mappings=field_mappings,
                    )
                )
                monday_added = True

    # Backward-compatible fallback: mappings.yaml + MONDAY_API_KEY
    if not monday_added:
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
