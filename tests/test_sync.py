"""Tests for sync engine."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock

import pytest

from research_agent.connectors.base import BaseConnector, NormalizedItem
from research_agent.sync.sync_all import SyncEngine
from tests.conftest import MockEmbeddingProvider


class FakeConnector(BaseConnector):
    def __init__(self, name: str, items: list[NormalizedItem]) -> None:
        self._name = name
        self._items = items

    @property
    def source_name(self) -> str:
        return self._name

    async def list_updated_items(self, since: datetime | None = None) -> list[NormalizedItem]:
        if since:
            since_aware = since if since.tzinfo else since.replace(tzinfo=timezone.utc)
            return [
                i for i in self._items
                if i.updated_at and i.updated_at.replace(tzinfo=timezone.utc) > since_aware
            ]
        return self._items

    def normalize_item(self, raw: Any) -> NormalizedItem:
        return raw


class FailingConnector(BaseConnector):
    @property
    def source_name(self) -> str:
        return "failing"

    async def list_updated_items(self, since: datetime | None = None) -> list[NormalizedItem]:
        raise RuntimeError("Connection failed")

    def normalize_item(self, raw: Any) -> NormalizedItem:
        raise RuntimeError("Normalize failed")


def _make_normalized(
    id: str = "test:001",
    source: str = "mock",
    title: str = "Test Item",
    body: str = "Test body",
) -> NormalizedItem:
    return NormalizedItem(
        id=id,
        source=source,
        type="feature_request",
        title=title,
        body=body,
        metadata={"tags": ["test"]},
        created_at=datetime(2025, 6, 15, tzinfo=timezone.utc),
        updated_at=datetime(2025, 6, 15, tzinfo=timezone.utc),
    )


@pytest.fixture
def mock_vector_store():
    store = AsyncMock()
    store.upsert = AsyncMock()
    store.upsert_batch = AsyncMock()
    store.delete_by_parent = AsyncMock()
    return store


class TestSyncEngine:
    @pytest.mark.asyncio
    async def test_sync_single_connector(self, db, mock_embedder, mock_vector_store):
        items = [_make_normalized(id=f"test:{i:03d}", title=f"Item {i}") for i in range(3)]
        connector = FakeConnector("test_source", items)

        engine = SyncEngine(
            db=db,
            vector_store=mock_vector_store,
            embedding_provider=mock_embedder,
            connectors=[connector],
        )

        result = await engine.sync_all()
        assert "test_source" in result["connectors"]
        stats = result["connectors"]["test_source"]
        assert stats["fetched"] == 3
        assert stats["changed"] == 3
        assert stats["errors"] == 0

    @pytest.mark.asyncio
    async def test_sync_idempotent(self, db, mock_embedder, mock_vector_store):
        """Second sync with unchanged items should produce no new embeddings."""
        items = [_make_normalized()]

        class AlwaysReturnConnector(FakeConnector):
            async def list_updated_items(self, since: datetime | None = None) -> list[NormalizedItem]:
                return self._items

        connector = AlwaysReturnConnector("test_source", items)
        engine = SyncEngine(
            db=db,
            vector_store=mock_vector_store,
            embedding_provider=mock_embedder,
            connectors=[connector],
        )

        await engine.sync_all()
        result = await engine.sync_all()
        stats = result["connectors"]["test_source"]
        assert stats["changed"] == 0
        assert stats["skipped"] == 1

    @pytest.mark.asyncio
    async def test_connector_failure_isolation(self, db, mock_embedder, mock_vector_store):
        good_items = [_make_normalized(id="good:001", source="mock")]
        good_connector = FakeConnector("good_source", good_items)
        bad_connector = FailingConnector()

        engine = SyncEngine(
            db=db,
            vector_store=mock_vector_store,
            embedding_provider=mock_embedder,
            connectors=[bad_connector, good_connector],
        )

        result = await engine.sync_all()
        assert result["connectors"]["failing"]["error"] is True
        assert result["connectors"]["good_source"]["fetched"] == 1
        assert result["connectors"]["good_source"]["changed"] == 1

    @pytest.mark.asyncio
    async def test_deleted_item_removes_vectors(self, db, mock_embedder, mock_vector_store):
        item = _make_normalized()
        connector = FakeConnector("test", [item])
        engine = SyncEngine(
            db=db,
            vector_store=mock_vector_store,
            embedding_provider=mock_embedder,
            connectors=[connector],
        )
        await engine.sync_all()

        deleted = _make_normalized()
        deleted.is_deleted = True
        connector2 = FakeConnector("test", [deleted])
        engine2 = SyncEngine(
            db=db,
            vector_store=mock_vector_store,
            embedding_provider=mock_embedder,
            connectors=[connector2],
        )
        result = await engine2.sync_all()
        mock_vector_store.delete_by_parent.assert_called()

    @pytest.mark.asyncio
    async def test_sync_state_persisted(self, db, mock_embedder, mock_vector_store):
        connector = FakeConnector("test_source", [_make_normalized()])
        engine = SyncEngine(
            db=db,
            vector_store=mock_vector_store,
            embedding_provider=mock_embedder,
            connectors=[connector],
        )
        await engine.sync_all()

        state = await db.get_sync_state("test_source")
        assert state is not None

    @pytest.mark.asyncio
    async def test_malformed_items_skipped(self, db, mock_embedder, mock_vector_store):
        """Items with no title/body should be skipped, not crash the sync."""
        malformed = NormalizedItem(
            id="bad:001", source="mock", type="bug", title="", body="",
            created_at=datetime(2025, 6, 15, tzinfo=timezone.utc),
            updated_at=datetime(2025, 6, 15, tzinfo=timezone.utc),
        )
        good = _make_normalized(id="good:001")
        connector = FakeConnector("test", [malformed, good])
        engine = SyncEngine(
            db=db,
            vector_store=mock_vector_store,
            embedding_provider=mock_embedder,
            connectors=[connector],
        )
        result = await engine.sync_all()
        stats = result["connectors"]["test"]
        assert stats["malformed"] == 1
        assert stats["changed"] == 1
