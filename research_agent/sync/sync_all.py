"""Sync engine — orchestrates connectors to keep data fresh.

Handles:
- Batch processing (100 items per batch) for large initial syncs
- Connector failure isolation (one fails, others continue)
- Auth error diagnostics (401/403 → clear message per source)
- Malformed item skip + log (never crash sync)
- Progress resumable on interruption via sync_state
- Writes to canonical schema (Entity + entity_fields + chunks).
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any
import json

from research_agent.connectors.base import BaseConnector, ConnectorError
from research_agent.embedding.chunker import chunk_text as chunk_text_embedding
from research_agent.embedding.base import EmbeddingProvider
from research_agent.storage.db import Database
from research_agent.storage.models import (
    Chunk as StorageChunk,
    Entity,
    EntityType,
    SourceSystem,
)
from research_agent.vector.qdrant_client import QdrantStore

logger = logging.getLogger(__name__)

BATCH_SIZE = 100

# Fields we chunk and embed
SEARCHABLE_FIELDS = {
    "title",          # include titles so items with no long description still become searchable
    "description",
    "transcript",
    "overview",
    "summary",
    "requirements",
    "success_metrics",
}


class ConnectorAuthError(Exception):
    """Raised when a connector encounters auth issues (401/403)."""

    def __init__(self, source: str, status_code: int) -> None:
        self.source = source
        self.status_code = status_code
        super().__init__(
            f"Authentication failed for {source} (HTTP {status_code}). "
            f"Check API key/token for the '{source}' connector."
        )


def _build_chunks_for_entity(entity: Entity) -> list[StorageChunk]:
    """Build storage chunks from entity's searchable text fields."""
    chunks: list[StorageChunk] = []
    for f in entity.fields:
        if f.field_name not in SEARCHABLE_FIELDS or not f.field_value or not f.field_value.strip():
            continue
        embedding_chunks = chunk_text_embedding(f.field_value, parent_id=entity.id)
        for c in embedding_chunks:
            chunks.append(
                StorageChunk(
                    id=f"{entity.id}:{f.field_name}:{c.index}",
                    field_name=f.field_name,
                    chunk_index=c.index,
                    text=c.text,
                )
            )
    return chunks


class SyncEngine:
    def __init__(
        self,
        db: Database,
        vector_store: QdrantStore,
        embedding_provider: EmbeddingProvider,
        connectors: list[BaseConnector],
    ) -> None:
        self._db = db
        self._vector = vector_store
        self._embedder = embedding_provider
        self._connectors = connectors

    def _merge_connector_stats(self, existing: dict[str, Any], new: dict[str, Any]) -> dict[str, Any]:
        """Merge stats from a connector into existing (same source, e.g. multiple boards)."""
        out = dict(existing) if existing else {}
        for key in ("fetched", "changed", "embedded", "errors", "skipped", "malformed"):
            out[key] = out.get(key, 0) + new.get(key, 0)
        out["duration_ms"] = out.get("duration_ms", 0) + new.get("duration_ms", 0)
        if new.get("error"):
            out["error"] = True
            out["message"] = out.get("message") or new.get("message", "Connector failed")
        return out

    async def sync_all(self) -> dict[str, Any]:
        """Run sync for all registered connectors. Failures are isolated per connector."""
        overall_start = time.time()
        results: dict[str, Any] = {}

        for connector in self._connectors:
            source = connector.source_name
            try:
                result = await self._sync_connector(connector)
                results[source] = self._merge_connector_stats(results.get(source), result)
                logger.info(
                    "Sync complete for %s",
                    source,
                    extra={
                        "source": source,
                        "count": result["fetched"],
                        "duration_ms": result["duration_ms"],
                    },
                )
            except ConnectorAuthError as e:
                logger.error(
                    "Auth failure for connector %s: %s",
                    source,
                    str(e),
                    extra={"source": source, "error_type": "auth_failure"},
                )
                results[source] = {
                    "error": True,
                    "error_type": "auth",
                    "message": str(e),
                }
            except ConnectorError as e:
                logger.error(
                    "Connector %s: %s",
                    source,
                    str(e),
                    extra={"source": source, "error_type": "connector_error"},
                )
                results[source] = {"error": True, "message": str(e)}
            except Exception:
                logger.exception(
                    "Connector %s failed — isolated, continuing with others",
                    source,
                    extra={"source": source, "error_type": "connector_failure"},
                )
                results[source] = {"error": True, "message": f"Connector {source} failed"}

        elapsed = int((time.time() - overall_start) * 1000)
        logger.info(
            "Sync all complete",
            extra={"duration_ms": elapsed, "count": len(self._connectors)},
        )
        return {"connectors": results, "total_duration_ms": elapsed}

    async def _sync_connector(self, connector: BaseConnector) -> dict[str, Any]:
        start = time.time()
        source = connector.source_name
        stats = {
            "fetched": 0,
            "changed": 0,
            "embedded": 0,
            "errors": 0,
            "skipped": 0,
            "malformed": 0,
        }

        sync_key = getattr(connector, "sync_state_key", source)
        last_synced = await self._db.get_sync_state(sync_key)
        is_first_sync = last_synced is None

        if is_first_sync:
            logger.info("First sync for %s — processing all items in batches", sync_key)

        entities = await connector.list_updated_items(since=last_synced)
        stats["fetched"] = len(entities)

        for batch_start in range(0, len(entities), BATCH_SIZE):
            batch = entities[batch_start : batch_start + BATCH_SIZE]
            batch_num = batch_start // BATCH_SIZE + 1
            total_batches = (len(entities) + BATCH_SIZE - 1) // BATCH_SIZE

            for entity in batch:
                try:
                    self._validate_entity(entity)
                    # Attach chunks from searchable fields before persisting
                    entity.chunks = _build_chunks_for_entity(entity)
                    changed = await self._process_entity(entity)
                    if changed:
                        stats["changed"] += 1
                        stats["embedded"] += 1
                    else:
                        stats["skipped"] += 1
                except ValueError as e:
                    stats["malformed"] += 1
                    logger.warning(
                        "Malformed entity skipped: %s from %s — %s",
                        entity.id,
                        source,
                        str(e),
                        extra={
                            "item_id": entity.id,
                            "source": source,
                            "error_type": "malformed_item",
                        },
                    )
                except Exception:
                    stats["errors"] += 1
                    logger.exception(
                        "Failed to process entity %s from %s",
                        entity.id,
                        source,
                        extra={"item_id": entity.id, "source": source},
                    )

            logger.info(
                "Sync %s: batch %d/%d (%d/%d items)",
                source,
                batch_num,
                total_batches,
                min(batch_start + BATCH_SIZE, len(entities)),
                len(entities),
                extra={"source": source},
            )

        await self._db.set_sync_state(sync_key, datetime.now(timezone.utc))
        stats["duration_ms"] = int((time.time() - start) * 1000)
        return stats

    @staticmethod
    def _validate_entity(entity: Entity) -> None:
        if not entity.id:
            raise ValueError("Entity missing id")
        if not entity.title and not entity.fields:
            raise ValueError(f"Entity {entity.id} has no title or fields")

    async def _process_entity(self, entity: Entity) -> bool:
        """Upsert entity to DB and Qdrant (with chunks). Returns True if new or changed."""
        changed = await self._db.upsert_entity(entity)
        if not changed:
            return False

        await self._vector.delete_by_parent(entity.id)

        if entity.is_deleted:
            return True

        if entity.chunks:
            texts = [c.text for c in entity.chunks]
            vectors = await self._embedder.embed_batch(texts)
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
            await self._vector.upsert_batch(points)

        return True
