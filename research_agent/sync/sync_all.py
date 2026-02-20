"""Sync engine — orchestrates all connectors to keep data fresh.

Handles:
- Batch processing (100 items per batch) for large initial syncs
- Connector failure isolation (one fails, others continue)
- Auth error diagnostics (401/403 → clear message per source)
- Malformed item skip + log (never crash sync)
- Progress resumable on interruption via sync_state
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any

from research_agent.connectors.base import BaseConnector, NormalizedItem
from research_agent.embedding.base import EmbeddingProvider
from research_agent.embedding.chunker import chunk_text
from research_agent.storage.db import Database
from research_agent.storage.models import Item, ItemSource, ItemType, compute_content_hash
from research_agent.vector.qdrant_client import QdrantStore

logger = logging.getLogger(__name__)

BATCH_SIZE = 100


class ConnectorAuthError(Exception):
    """Raised when a connector encounters auth issues (401/403)."""

    def __init__(self, source: str, status_code: int) -> None:
        self.source = source
        self.status_code = status_code
        super().__init__(
            f"Authentication failed for {source} (HTTP {status_code}). "
            f"Check API key/token for the '{source}' connector."
        )


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

    async def sync_all(self) -> dict[str, Any]:
        """Run sync for all registered connectors. Failures are isolated per connector."""
        overall_start = time.time()
        results: dict[str, Any] = {}

        for connector in self._connectors:
            source = connector.source_name
            try:
                result = await self._sync_connector(connector)
                results[source] = result
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

        last_synced = await self._db.get_sync_state(source)
        is_first_sync = last_synced is None

        if is_first_sync:
            logger.info("First sync for %s — processing all items in batches", source)

        items = await connector.list_updated_items(since=last_synced)
        stats["fetched"] = len(items)

        for batch_start in range(0, len(items), BATCH_SIZE):
            batch = items[batch_start : batch_start + BATCH_SIZE]
            batch_num = batch_start // BATCH_SIZE + 1
            total_batches = (len(items) + BATCH_SIZE - 1) // BATCH_SIZE

            for normalized in batch:
                try:
                    self._validate_item(normalized)
                    changed = await self._process_item(normalized)
                    if changed:
                        stats["changed"] += 1
                        stats["embedded"] += 1
                    else:
                        stats["skipped"] += 1
                except ValueError as e:
                    stats["malformed"] += 1
                    logger.warning(
                        "Malformed item skipped: %s from %s — %s",
                        normalized.id, source, str(e),
                        extra={
                            "item_id": normalized.id,
                            "source": source,
                            "error_type": "malformed_item",
                        },
                    )
                except Exception:
                    stats["errors"] += 1
                    logger.exception(
                        "Failed to process item %s from %s",
                        normalized.id,
                        source,
                        extra={"item_id": normalized.id, "source": source},
                    )

            logger.info(
                "Sync %s: batch %d/%d (%d/%d items)",
                source,
                batch_num,
                total_batches,
                min(batch_start + BATCH_SIZE, len(items)),
                len(items),
                extra={"source": source},
            )

        await self._db.set_sync_state(source, datetime.now(timezone.utc))
        stats["duration_ms"] = int((time.time() - start) * 1000)
        return stats

    @staticmethod
    def _validate_item(item: NormalizedItem) -> None:
        """Raise ValueError if item is malformed."""
        if not item.id:
            raise ValueError("Item missing id")
        if not item.title and not item.body:
            raise ValueError(f"Item {item.id} has no title or body")

    async def _process_item(self, normalized: NormalizedItem) -> bool:
        """Convert normalized item to canonical Item, upsert to DB + Qdrant."""
        content_hash = compute_content_hash(normalized.title, normalized.body)

        existing = await self._db.get_item(normalized.id)
        if existing and existing.content_hash == content_hash and not normalized.is_deleted:
            return False

        try:
            source_enum = ItemSource(normalized.source)
        except ValueError:
            source_enum = ItemSource.MOCK

        try:
            type_enum = ItemType(normalized.type)
        except ValueError:
            type_enum = ItemType.FEATURE_REQUEST

        item = Item(
            id=normalized.id,
            source=source_enum,
            type=type_enum,
            title=normalized.title,
            body=normalized.body,
            metadata=normalized.metadata,
            created_at=normalized.created_at or datetime.now(timezone.utc),
            updated_at=normalized.updated_at or datetime.now(timezone.utc),
            is_deleted=normalized.is_deleted,
        )

        await self._db.upsert_item(item)

        if item.is_deleted:
            await self._vector.delete_by_parent(item.id)
        else:
            await self._embed_and_upsert(item)

        return True

    async def _embed_and_upsert(self, item: Item) -> None:
        embed_text = f"{item.title}\n\n{item.body}"
        chunks = chunk_text(embed_text, parent_id=item.id)

        await self._vector.delete_by_parent(item.id)

        if len(chunks) == 1:
            vector = await self._embedder.embed(chunks[0].text)
            await self._vector.upsert(
                point_id=item.id,
                vector=vector,
                payload=self._build_payload(item, 0),
            )
        else:
            texts = [c.text for c in chunks]
            vectors = await self._embedder.embed_batch(texts)
            points: list[tuple[str, list[float], dict[str, Any]]] = []
            for chunk, vector in zip(chunks, vectors):
                chunk_id = f"{item.id}:chunk:{chunk.index}"
                points.append((chunk_id, vector, self._build_payload(item, chunk.index)))
            await self._vector.upsert_batch(points)

    @staticmethod
    def _build_payload(item: Item, chunk_index: int) -> dict[str, Any]:
        return {
            "parent_id": item.id,
            "chunk_index": chunk_index,
            "title": item.title,
            "body": item.body[:2000],
            "source": item.source.value,
            "type": item.type.value,
            "metadata": item.metadata,
            "tags": item.metadata.get("tags", []),
            "created_at": item.created_at.isoformat(),
            "updated_at": item.updated_at.isoformat(),
        }
