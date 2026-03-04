"""Reindex command — migrate vectors from local Qdrant storage to a running Qdrant server.

Usage: python -m research_agent reindex

Reads all entities from SQLite, re-embeds them, and upserts to the Qdrant server.
This is used when upgrading from local mode to Docker/server mode.
"""

from __future__ import annotations

import asyncio
import logging
import time

from research_agent.config.loader import get_settings
from research_agent.embedding.openai_provider import OpenAIEmbeddingProvider
from research_agent.storage.db import Database
from research_agent.vector.qdrant_client import QdrantStore

logger = logging.getLogger(__name__)

GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
BOLD = "\033[1m"
RESET = "\033[0m"


async def _run_reindex() -> None:
    settings = get_settings()

    if settings.qdrant_mode != "server":
        print(f"\n{RED}QDRANT_MODE must be set to 'server' before reindexing.{RESET}")
        print(f"  1. Set QDRANT_MODE=server in .env")
        print(f"  2. Ensure Qdrant server is running (docker-compose up qdrant -d)")
        print(f"  3. Re-run: python -m research_agent reindex\n")
        return

    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    print(f"\n{BOLD}Reindex: migrating data to Qdrant server{RESET}\n")

    db = Database(db_path=settings.database_path)
    await db.init()

    vector_store = QdrantStore(host=settings.qdrant_host, port=settings.qdrant_port)
    embedder = OpenAIEmbeddingProvider(
        api_key=settings.openai_api_key, model=settings.embedding_model,
    )

    try:
        await vector_store.ensure_collection(embedder.dimension())
    except Exception as e:
        print(f"{RED}Cannot connect to Qdrant server at {settings.qdrant_host}:{settings.qdrant_port}{RESET}")
        print(f"  Error: {e}")
        print(f"  Make sure docker-compose up qdrant -d is running.\n")
        await db.close()
        return

    from research_agent.storage.models import EntityRow
    from sqlalchemy import select

    start = time.time()
    count = 0

    async with db._async_session() as session:
        result = await session.execute(select(EntityRow).where(EntityRow.is_deleted == False))  # noqa: E712
        entities = result.scalars().all()

        print(f"  Found {len(entities)} entities in database.")

        for entity_row in entities:
            await session.refresh(entity_row, ["chunks"])
            for chunk in entity_row.chunks:
                try:
                    vectors = await embedder.embed_batch([chunk.text])
                    if vectors:
                        await vector_store.upsert(
                            point_id=chunk.id,
                            vector=vectors[0],
                            payload={
                                "parent_id": entity_row.id,
                                "entity_type": entity_row.entity_type,
                                "source": entity_row.source_system,
                                "title": entity_row.title,
                                "field_name": chunk.field_name,
                                "text": chunk.text,
                                "created_at": entity_row.created_at.isoformat()
                                if entity_row.created_at
                                else "",
                            },
                        )
                        count += 1
                except Exception:
                    logger.warning("Failed to reindex chunk %s", chunk.id, exc_info=True)

    elapsed = time.time() - start
    server_count = await vector_store.count()

    print(f"\n  {GREEN}✓{RESET} Reindexed {count} vectors in {elapsed:.1f}s")
    print(f"  {GREEN}✓{RESET} Qdrant server now has {server_count:,} vectors")
    print(f"\n  {BOLD}Next steps:{RESET}")
    print(f"  1. Restart the API: python -m research_agent serve")
    print(f"  2. Verify: python -m research_agent doctor\n")

    await vector_store.close()
    await db.close()


def run_reindex() -> None:
    asyncio.run(_run_reindex())
