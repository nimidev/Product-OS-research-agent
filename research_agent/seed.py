"""Seed command — load JSON fixtures into SQLite + embed and upsert to Qdrant."""

from __future__ import annotations

import asyncio
import json
import logging
import sys
import time
from pathlib import Path

from research_agent.config.loader import get_settings
from research_agent.embedding.openai_provider import OpenAIEmbeddingProvider
from research_agent.memory.memory_service import MemoryService
from research_agent.storage.db import Database
from research_agent.storage.models import Item, ItemSource, ItemType
from research_agent.synthesis.summarizer import Summarizer
from research_agent.vector.qdrant_client import QdrantStore

logger = logging.getLogger(__name__)

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "data" / "fixtures"

TYPE_MAP: dict[str, ItemType] = {
    "feature_requests": ItemType.FEATURE_REQUEST,
    "bugs": ItemType.BUG,
    "roadmap_items": ItemType.ROADMAP_ITEM,
    "meeting_notes": ItemType.MEETING_NOTE,
    "prds": ItemType.PRD,
    "support_tickets": ItemType.SUPPORT_TICKET,
}


def _load_fixtures() -> list[Item]:
    """Load all JSON fixture files from data/fixtures/."""
    items: list[Item] = []

    if not FIXTURES_DIR.exists():
        logger.warning("Fixtures directory not found: %s", FIXTURES_DIR)
        return items

    for file_path in sorted(FIXTURES_DIR.glob("*.json")):
        stem = file_path.stem
        item_type = TYPE_MAP.get(stem)
        if item_type is None:
            logger.warning("Unknown fixture type: %s, skipping", stem)
            continue

        with open(file_path) as f:
            data = json.load(f)

        if not isinstance(data, list):
            logger.warning("Fixture %s is not a list, skipping", file_path.name)
            continue

        for raw in data:
            try:
                item = Item(
                    id=raw["id"],
                    source=ItemSource(raw.get("source", "mock")),
                    type=item_type,
                    title=raw["title"],
                    body=raw.get("body", ""),
                    metadata=raw.get("metadata", {}),
                    created_at=raw.get("created_at", None),
                    updated_at=raw.get("updated_at", None),
                )
                items.append(item)
            except Exception:
                logger.exception("Failed to parse item from %s: %s", file_path.name, raw.get("id"))

    return items


async def run_seed() -> None:
    settings = get_settings()

    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    logger.info("Starting seed process...")
    start = time.time()

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

    memory = MemoryService(
        db=db,
        vector_store=vector_store,
        embedding_provider=embedding,
        summarizer=summarizer,
    )

    items = _load_fixtures()
    if not items:
        logger.error("No fixture items found. Check data/fixtures/ directory.")
        await vector_store.close()
        await db.close()
        return

    logger.info("Loaded %d items from fixtures", len(items))
    seeded = 0
    skipped = 0

    for i, item in enumerate(items, 1):
        try:
            changed = await memory.add_or_update_item(item)
            if changed:
                seeded += 1
            else:
                skipped += 1
            if i % 50 == 0 or i == len(items):
                logger.info("Progress: %d/%d items processed (%d new/changed, %d unchanged)",
                            i, len(items), seeded, skipped)
        except Exception:
            logger.exception("Failed to seed item %s", item.id)

    elapsed = time.time() - start
    logger.info(
        "Seed complete: %d seeded, %d skipped (unchanged), %.1fs elapsed",
        seeded, skipped, elapsed,
    )

    await vector_store.close()
    await db.close()


def main() -> None:
    asyncio.run(run_seed())


if __name__ == "__main__":
    main()
