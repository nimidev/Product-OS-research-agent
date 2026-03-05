"""Tests for Qdrant vector store (mocked client)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from research_agent.vector.qdrant_client import COLLECTION_NAME, QdrantStore, SearchResult
from research_agent.config.loader import create_vector_store, Settings


@dataclass
class FakeCollection:
    name: str


@dataclass
class FakeCollections:
    collections: list[FakeCollection]


@dataclass
class FakeScoredPoint:
    id: str
    score: float
    payload: dict[str, Any]


@dataclass
class FakeQueryResponse:
    points: list[FakeScoredPoint]


@pytest.fixture
def mock_qdrant():
    with patch("research_agent.vector.qdrant_client.AsyncQdrantClient") as MockClient:
        client = AsyncMock()
        MockClient.return_value = client
        client.get_collections = AsyncMock(return_value=FakeCollections(collections=[]))
        client.create_collection = AsyncMock()
        client.upsert = AsyncMock()
        client.delete = AsyncMock()
        client.close = AsyncMock()

        store = QdrantStore.__new__(QdrantStore)
        store._client = client
        yield store, client


class TestQdrantStore:
    @pytest.mark.asyncio
    async def test_ensure_collection_creates(self, mock_qdrant):
        store, client = mock_qdrant
        client.get_collections = AsyncMock(
            return_value=FakeCollections(collections=[])
        )
        await store.ensure_collection(dimension=128)
        client.create_collection.assert_called_once()

    @pytest.mark.asyncio
    async def test_ensure_collection_exists(self, mock_qdrant):
        store, client = mock_qdrant
        client.get_collections = AsyncMock(
            return_value=FakeCollections(
                collections=[FakeCollection(name=COLLECTION_NAME)]
            )
        )
        await store.ensure_collection(dimension=128)
        client.create_collection.assert_not_called()

    @pytest.mark.asyncio
    async def test_upsert(self, mock_qdrant):
        store, client = mock_qdrant
        await store.upsert("point1", [0.1] * 128, {"title": "test"})
        client.upsert.assert_called_once()

    @pytest.mark.asyncio
    async def test_search_dedup_by_parent(self, mock_qdrant):
        store, client = mock_qdrant
        client.query_points = AsyncMock(
            return_value=FakeQueryResponse(
                points=[
                    FakeScoredPoint(
                        id="item1:chunk:0",
                        score=0.95,
                        payload={"parent_id": "item1", "title": "First"},
                    ),
                    FakeScoredPoint(
                        id="item1:chunk:1",
                        score=0.85,
                        payload={"parent_id": "item1", "title": "First"},
                    ),
                    FakeScoredPoint(
                        id="item2:chunk:0",
                        score=0.90,
                        payload={"parent_id": "item2", "title": "Second"},
                    ),
                ]
            )
        )

        results = await store.search([0.1] * 128, top_k=5)
        assert len(results) == 2
        assert results[0].parent_id == "item1"
        assert results[0].score == 0.95
        assert results[1].parent_id == "item2"

    @pytest.mark.asyncio
    async def test_search_top_k_limit(self, mock_qdrant):
        store, client = mock_qdrant
        points = [
            FakeScoredPoint(
                id=f"item{i}:chunk:0",
                score=1.0 - i * 0.1,
                payload={"parent_id": f"item{i}", "title": f"Item {i}"},
            )
            for i in range(10)
        ]
        client.query_points = AsyncMock(
            return_value=FakeQueryResponse(points=points)
        )

        results = await store.search([0.1] * 128, top_k=3)
        assert len(results) == 3

    @pytest.mark.asyncio
    async def test_delete(self, mock_qdrant):
        store, client = mock_qdrant
        await store.delete(["point1", "point2"])
        client.delete.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_empty(self, mock_qdrant):
        store, client = mock_qdrant
        await store.delete([])
        client.delete.assert_not_called()

    @pytest.mark.asyncio
    async def test_upsert_batch(self, mock_qdrant):
        store, client = mock_qdrant
        points = [
            (f"p{i}", [0.1] * 128, {"title": f"Item {i}"}) for i in range(5)
        ]
        await store.upsert_batch(points)
        client.upsert.assert_called_once()


class TestQdrantStoreInit:
    """Test QdrantStore constructor modes and create_vector_store factory."""

    @patch("research_agent.vector.qdrant_client.AsyncQdrantClient")
    def test_server_mode(self, mock_client_cls):
        store = QdrantStore(host="myhost", port=1234)
        mock_client_cls.assert_called_once_with(host="myhost", port=1234)
        assert store.mode == "server"

    @patch("research_agent.vector.qdrant_client.AsyncQdrantClient")
    def test_local_mode(self, mock_client_cls):
        store = QdrantStore(path="./test_data")
        mock_client_cls.assert_called_once_with(path="./test_data")
        assert store.mode == "local"

    @patch("research_agent.vector.qdrant_client.AsyncQdrantClient")
    def test_factory_local(self, mock_client_cls):
        settings = Settings(qdrant_mode="local", qdrant_local_path="./my_data")
        store = create_vector_store(settings)
        mock_client_cls.assert_called_once_with(path="./my_data")
        assert store.mode == "local"

    @patch("research_agent.vector.qdrant_client.AsyncQdrantClient")
    def test_factory_server(self, mock_client_cls):
        settings = Settings(qdrant_mode="server", qdrant_host="qdrant.local", qdrant_port=9999)
        store = create_vector_store(settings)
        mock_client_cls.assert_called_once_with(host="qdrant.local", port=9999)
        assert store.mode == "server"
