"""Seed command — load canonical JSON fixtures into entities + entity_fields + chunks, embed and upsert to Qdrant."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path

from research_agent.config.loader import create_vector_store, get_settings
from research_agent.embedding.chunker import chunk_text as chunk_text_embedding
from research_agent.embedding.openai_provider import OpenAIEmbeddingProvider
from research_agent.storage.db import Database
from research_agent.storage.models import (
    Chunk as StorageChunk,
    Entity,
    EntityField,
    EntityType,
    SourceSystem,
)

logger = logging.getLogger(__name__)

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "data" / "fixtures"

# Fixture file stem -> entity type
ENTITY_TYPE_MAP: dict[str, EntityType] = {
    "feature_requests": EntityType.FEATURE_REQUEST,
    "bugs": EntityType.BUG,
    "roadmap_items": EntityType.ROADMAP_ITEM,
    "meeting_notes": EntityType.MEETING_NOTE,
    "prds": EntityType.PRD,
    "support_tickets": EntityType.SUPPORT_TICKET,
}

# Fields we chunk and embed (long text); others only in entity_fields
SEARCHABLE_FIELDS = {"description", "transcript", "overview", "summary", "requirements", "success_metrics"}


def _parse_datetime(s: str | None) -> datetime:
    if not s:
        return datetime.now(timezone.utc)
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return datetime.now(timezone.utc)


def _load_canonical_fixtures() -> list[Entity]:
    """Load canonical JSON fixtures into Entity objects with fields and chunks."""
    entities: list[Entity] = []

    if not FIXTURES_DIR.exists():
        logger.warning("Fixtures directory not found: %s", FIXTURES_DIR)
        return entities

    for file_path in sorted(FIXTURES_DIR.glob("*.json")):
        stem = file_path.stem
        entity_type = ENTITY_TYPE_MAP.get(stem)
        if entity_type is None:
            logger.warning("Unknown fixture type: %s, skipping", stem)
            continue

        with open(file_path) as f:
            data = json.load(f)

        if not isinstance(data, list):
            logger.warning("Fixture %s is not a list, skipping", file_path.name)
            continue

        for raw in data:
            try:
                entity_id = raw["id"]
                source_id = raw.get("source_id", entity_id.split(":")[-1] if ":" in entity_id else entity_id)
                title = raw.get("title", "")
                fields_dict = raw.get("fields", {})

                fields_list = [
                    EntityField(field_name=k, field_type="text", field_value=str(v))
                    for k, v in fields_dict.items()
                ]
                # Include title in fields for content_hash
                if not any(f.field_name == "title" for f in fields_list):
                    fields_list.insert(0, EntityField(field_name="title", field_type="text", field_value=title))

                created = _parse_datetime(raw.get("created_at"))
                updated = _parse_datetime(raw.get("updated_at"))

                chunks: list[StorageChunk] = []
                for fn, fv in fields_dict.items():
                    if fn not in SEARCHABLE_FIELDS or not fv or not str(fv).strip():
                        continue
                    text = str(fv)
                    embedding_chunks = chunk_text_embedding(text, parent_id=entity_id)
                    for c in embedding_chunks:
                        chunks.append(
                            StorageChunk(
                                id=f"{entity_id}:{fn}:{c.index}",
                                field_name=fn,
                                chunk_index=c.index,
                                text=c.text,
                            )
                        )

                entity = Entity(
                    id=entity_id,
                    entity_type=entity_type,
                    source_system=SourceSystem(raw.get("source", "mock")),
                    source_id=source_id,
                    title=title,
                    fields=fields_list,
                    chunks=chunks,
                    created_at=created,
                    updated_at=updated,
                    is_deleted=False,
                )
                entities.append(entity)
            except Exception:
                logger.exception("Failed to parse fixture from %s: %s", file_path.name, raw.get("id"))

    return entities


async def run_seed() -> None:
    settings = get_settings()

    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    logger.info("Starting seed process (canonical entity model)...")
    start = time.time()

    db = Database(db_path=settings.database_path)
    await db.init()

    vector_store = create_vector_store(settings)
    embedding = OpenAIEmbeddingProvider(
        api_key=settings.openai_api_key, model=settings.embedding_model,
    )
    await vector_store.ensure_collection(embedding.dimension())

    entities = _load_canonical_fixtures()
    if not entities:
        logger.error("No fixture entities found. Check data/fixtures/ directory.")
        await vector_store.close()
        await db.close()
        return

    logger.info("Loaded %d entities from fixtures", len(entities))
    seeded = 0
    skipped = 0

    for i, entity in enumerate(entities, 1):
        try:
            changed = await db.upsert_entity(entity)
            if changed:
                await vector_store.delete_by_parent(entity.id)
                if entity.chunks:
                    texts = [c.text for c in entity.chunks]
                    vectors = await embedding.embed_batch(texts)
                    points = [
                        (
                            c.id,
                            vec,
                            {
                                "parent_id": entity.id,
                                "entity_type": entity.entity_type.value,
                                "field_name": c.field_name,
                                "title": entity.title,
                                "source": entity.source_system.value,
                                "body": c.text[:2000],
                                "chunk_index": c.chunk_index,
                                "created_at": entity.created_at.isoformat() if entity.created_at else "",
                                "updated_at": entity.updated_at.isoformat() if entity.updated_at else "",
                            },
                        )
                        for c, vec in zip(entity.chunks, vectors, strict=True)
                    ]
                    await vector_store.upsert_batch(points)
                seeded += 1
            else:
                skipped += 1
            if i % 50 == 0 or i == len(entities):
                logger.info(
                    "Progress: %d/%d entities (%d new/changed, %d unchanged)",
                    i, len(entities), seeded, skipped,
                )
        except Exception:
            logger.exception("Failed to seed entity %s", entity.id)

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
