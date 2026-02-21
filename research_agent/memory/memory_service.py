"""Core memory service — search (with field-aware + flexible scope) and add/update entities."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from research_agent.embedding.base import EmbeddingProvider
from research_agent.embedding.chunker import chunk_text
from research_agent.storage.db import Database
from research_agent.storage.models import Entity
from research_agent.synthesis.summarizer import Summarizer, SynthesisResult
from research_agent.vector.qdrant_client import QdrantStore, SearchResult

from research_agent.memory.query_understanding import infer_entity_scope

logger = logging.getLogger(__name__)

SEARCHABLE_FIELDS = {
    "description", "transcript", "overview", "summary",
    "requirements", "success_metrics",
}


@dataclass
class MemorySearchResult:
    summary: str
    references: list[dict[str, Any]]
    raw_results: list[dict[str, Any]]
    degraded: bool = False


def _search_result_to_dict(sr: SearchResult) -> dict[str, Any]:
    payload = sr.payload
    return {
        "id": sr.parent_id,
        "score": sr.score,
        "title": payload.get("title", ""),
        "body": payload.get("body", ""),
        "source": payload.get("source", ""),
        "type": payload.get("entity_type", payload.get("type", "")),
        "entity_type": payload.get("entity_type", ""),
        "field_name": payload.get("field_name", ""),
        "metadata": payload.get("metadata", {}),
        "created_at": payload.get("created_at", ""),
    }


class MemoryService:
    def __init__(
        self,
        db: Database,
        vector_store: QdrantStore,
        embedding_provider: EmbeddingProvider,
        summarizer: Summarizer | None = None,
    ) -> None:
        self._db = db
        self._vector = vector_store
        self._embedder = embedding_provider
        self._summarizer = summarizer

    @staticmethod
    def _build_context_aware_query(query: str, context: str | None) -> str:
        if not context:
            return query
        return f"Previous research context:\n{context}\n\nCurrent question: {query}"

    async def search_memories(
        self,
        query: str,
        top_k: int = 10,
        entity_types: list[str] | None = None,
        field_names: list[str] | None = None,
        source: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        tags: list[str] | None = None,
        context: str | None = None,
        use_query_understanding: bool = True,
    ) -> MemorySearchResult:
        """Search with optional entity/field scope. When entity_types/field_names are
        omitted or empty, infers scope from query + context if use_query_understanding
        is True; otherwise searches all.
        """
        search_query = self._build_context_aware_query(query, context)
        query_vector = await self._embedder.embed(search_query)

        if use_query_understanding and entity_types is None and field_names is None:
            inferred_types, inferred_fields = infer_entity_scope(query, context)
            entity_types = inferred_types if inferred_types else None
            field_names = inferred_fields if inferred_fields else None

        results = await self._vector.search(
            query_vector=query_vector,
            top_k=top_k,
            source=source,
            entity_types=entity_types,
            field_names=field_names,
            date_from=date_from,
            date_to=date_to,
            tags=tags,
        )

        raw_results = [_search_result_to_dict(r) for r in results]

        if self._summarizer and raw_results:
            synthesis = await self._summarizer.synthesize(query, raw_results, context)
            return MemorySearchResult(
                summary=synthesis.summary,
                references=[
                    {
                        "title": ref.title,
                        "url": ref.url,
                        "source": ref.source,
                        "type": ref.type,
                    }
                    for ref in synthesis.references
                ],
                raw_results=raw_results,
                degraded=synthesis.degraded,
            )

        return MemorySearchResult(
            summary="Synthesis unavailable. Raw results provided.",
            references=[],
            raw_results=raw_results,
            degraded=True,
        )

    async def add_or_update_entity(self, entity: Entity) -> bool:
        """Upsert entity to SQLite and embed + upsert chunks to Qdrant. Returns True if changed."""
        from research_agent.storage.models import Chunk as StorageChunk

        changed = await self._db.upsert_entity(entity)
        if not changed:
            return False

        await self._vector.delete_by_parent(entity.id)

        if entity.is_deleted:
            return True

        chunks_list: list[StorageChunk] = []
        for f in entity.fields:
            if f.field_name not in SEARCHABLE_FIELDS or not f.field_value or not f.field_value.strip():
                continue
            for c in chunk_text(f.field_value, parent_id=entity.id):
                chunks_list.append(
                    StorageChunk(
                        id=f"{entity.id}:{f.field_name}:{c.index}",
                        field_name=f.field_name,
                        chunk_index=c.index,
                        text=c.text,
                    )
                )

        if chunks_list:
            texts = [c.text for c in chunks_list]
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
                for c, vec in zip(chunks_list, vectors, strict=True)
            ]
            await self._vector.upsert_batch(points)

        return True
