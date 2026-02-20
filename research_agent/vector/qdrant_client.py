"""Qdrant vector store wrapper with upsert/search/delete and parent_id dedup."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from qdrant_client import AsyncQdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    PointStruct,
    Range,
    VectorParams,
)

logger = logging.getLogger(__name__)

COLLECTION_NAME = "research_items"


@dataclass
class SearchResult:
    id: str
    parent_id: str
    score: float
    payload: dict[str, Any] = field(default_factory=dict)


class QdrantStore:
    def __init__(self, host: str = "localhost", port: int = 6333) -> None:
        self._client = AsyncQdrantClient(host=host, port=port)

    async def ensure_collection(self, dimension: int) -> None:
        collections = await self._client.get_collections()
        names = [c.name for c in collections.collections]
        if COLLECTION_NAME not in names:
            await self._client.create_collection(
                collection_name=COLLECTION_NAME,
                vectors_config=VectorParams(size=dimension, distance=Distance.COSINE),
            )
            logger.info("Created collection %s (dim=%d)", COLLECTION_NAME, dimension)

    async def upsert(
        self,
        point_id: str,
        vector: list[float],
        payload: dict[str, Any],
    ) -> None:
        await self._client.upsert(
            collection_name=COLLECTION_NAME,
            points=[PointStruct(id=point_id, vector=vector, payload=payload)],
        )

    async def upsert_batch(
        self,
        points: list[tuple[str, list[float], dict[str, Any]]],
    ) -> None:
        if not points:
            return
        structs = [
            PointStruct(id=pid, vector=vec, payload=pay) for pid, vec, pay in points
        ]
        batch_size = 100
        for i in range(0, len(structs), batch_size):
            await self._client.upsert(
                collection_name=COLLECTION_NAME,
                points=structs[i : i + batch_size],
            )

    async def search(
        self,
        query_vector: list[float],
        top_k: int = 10,
        source: str | None = None,
        item_type: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        tags: list[str] | None = None,
    ) -> list[SearchResult]:
        conditions: list[Any] = []
        if source:
            conditions.append(FieldCondition(key="source", match=MatchValue(value=source)))
        if item_type:
            conditions.append(FieldCondition(key="type", match=MatchValue(value=item_type)))
        if date_from or date_to:
            range_params: dict[str, Any] = {}
            if date_from:
                range_params["gte"] = date_from
            if date_to:
                range_params["lte"] = date_to
            conditions.append(FieldCondition(key="created_at", range=Range(**range_params)))
        if tags:
            for tag in tags:
                conditions.append(FieldCondition(key="tags", match=MatchValue(value=tag)))

        query_filter = Filter(must=conditions) if conditions else None

        # Fetch more than top_k to account for dedup
        fetch_limit = top_k * 3

        results = await self._client.query_points(
            collection_name=COLLECTION_NAME,
            query=query_vector,
            query_filter=query_filter,
            limit=fetch_limit,
            with_payload=True,
        )

        return self._dedup_by_parent(results.points, top_k)

    def _dedup_by_parent(
        self, points: list[Any], top_k: int
    ) -> list[SearchResult]:
        """Keep the best-scoring chunk per parent_id."""
        seen: dict[str, SearchResult] = {}
        for point in points:
            payload = point.payload or {}
            parent_id = payload.get("parent_id", str(point.id))
            score = point.score
            if parent_id not in seen or score > seen[parent_id].score:
                seen[parent_id] = SearchResult(
                    id=str(point.id),
                    parent_id=parent_id,
                    score=score,
                    payload=payload,
                )
        ranked = sorted(seen.values(), key=lambda r: r.score, reverse=True)
        return ranked[:top_k]

    async def delete(self, point_ids: list[str]) -> None:
        if not point_ids:
            return
        from qdrant_client.models import PointIdsList

        await self._client.delete(
            collection_name=COLLECTION_NAME,
            points_selector=PointIdsList(points=point_ids),
        )

    async def delete_by_parent(self, parent_id: str) -> None:
        await self._client.delete(
            collection_name=COLLECTION_NAME,
            points_selector=Filter(
                must=[FieldCondition(key="parent_id", match=MatchValue(value=parent_id))]
            ),
        )

    async def count(self) -> int:
        info = await self._client.get_collection(COLLECTION_NAME)
        return info.points_count or 0

    async def close(self) -> None:
        await self._client.close()
