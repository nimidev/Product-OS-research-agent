"""Core memory service — search and add/update items via SQLite + Qdrant."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from research_agent.embedding.base import EmbeddingProvider
from research_agent.embedding.chunker import Chunk, chunk_text
from research_agent.storage.db import Database
from research_agent.storage.models import Item
from research_agent.synthesis.summarizer import Summarizer, SynthesisResult
from research_agent.vector.qdrant_client import QdrantStore, SearchResult

logger = logging.getLogger(__name__)


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
        "type": payload.get("type", ""),
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
        """Combine current query with conversation context for better vector search.

        Places context first so the embedding captures the ongoing research topic,
        then the current question refines focus.
        """
        if not context:
            return query
        return f"Previous research context:\n{context}\n\nCurrent question: {query}"

    async def search_memories(
        self,
        query: str,
        top_k: int = 10,
        source: str | None = None,
        item_type: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        tags: list[str] | None = None,
        context: str | None = None,
    ) -> MemorySearchResult:
        search_query = self._build_context_aware_query(query, context)
        query_vector = await self._embedder.embed(search_query)

        results = await self._vector.search(
            query_vector=query_vector,
            top_k=top_k,
            source=source,
            item_type=item_type,
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
                    {"title": ref.title, "url": ref.url, "source": ref.source, "type": ref.type}
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

    async def add_or_update_item(self, item: Item) -> bool:
        """Upsert item to SQLite and embed + upsert to Qdrant. Returns True if changed."""
        changed = await self._db.upsert_item(item)
        if not changed:
            return False

        if item.is_deleted:
            await self._vector.delete_by_parent(item.id)
            return True

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
                payload=self._build_payload(item, chunks[0]),
            )
        else:
            texts = [c.text for c in chunks]
            vectors = await self._embedder.embed_batch(texts)
            points: list[tuple[str, list[float], dict[str, Any]]] = []
            for chunk, vector in zip(chunks, vectors):
                chunk_id = f"{item.id}:chunk:{chunk.index}"
                points.append((chunk_id, vector, self._build_payload(item, chunk)))
            await self._vector.upsert_batch(points)

    def _build_payload(self, item: Item, chunk: Chunk) -> dict[str, Any]:
        return {
            "parent_id": item.id,
            "chunk_index": chunk.index,
            "title": item.title,
            "body": item.body[:2000],
            "source": item.source.value,
            "type": item.type.value,
            "metadata": item.metadata,
            "tags": item.metadata.get("tags", []),
            "created_at": item.created_at.isoformat(),
            "updated_at": item.updated_at.isoformat(),
        }
