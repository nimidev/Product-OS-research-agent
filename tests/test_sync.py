"""Tests for sync engine."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock

import pytest

from research_agent.connectors.base import BaseConnector
from research_agent.sync.sync_all import SyncEngine
from tests.conftest import make_entity, MockEmbeddingProvider


class FakeConnector(BaseConnector):
    def __init__(self, name: str, entities: list) -> None:
        self._name = name
        self._entities = entities

    @property
    def source_name(self) -> str:
        return self._name

    @property
    def entity_type(self) -> str:
        return "feature_request"

    async def list_updated_items(self, since: datetime | None = None) -> list:
        if since:
            since_aware = since if since.tzinfo else since.replace(tzinfo=timezone.utc)
            return [
                e for e in self._entities
                if e.updated_at and e.updated_at.replace(tzinfo=timezone.utc) > since_aware
            ]
        return self._entities

    def normalize_item(self, raw: Any) -> None:
        return raw


class FailingConnector(BaseConnector):
    @property
    def source_name(self) -> str:
        return "failing"

    @property
    def entity_type(self) -> str:
        return "feature_request"

    async def list_updated_items(self, since: datetime | None = None) -> list:
        raise RuntimeError("Connection failed")

    def normalize_item(self, raw: Any) -> None:
        raise RuntimeError("Normalize failed")


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
        entities = [make_entity(id=f"test:{i:03d}", title=f"Item {i}") for i in range(3)]
        connector = FakeConnector("test_source", entities)

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
        """Second sync with unchanged entities should produce no new embeddings."""
        entities = [make_entity()]

        class AlwaysReturnConnector(FakeConnector):
            async def list_updated_items(self, since=None):
                return self._entities

        connector = AlwaysReturnConnector("test_source", entities)
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
        good_entities = [make_entity(id="good:001")]
        good_connector = FakeConnector("good_source", good_entities)
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
        entity = make_entity()
        connector = FakeConnector("test", [entity])
        engine = SyncEngine(
            db=db,
            vector_store=mock_vector_store,
            embedding_provider=mock_embedder,
            connectors=[connector],
        )
        await engine.sync_all()

        deleted = make_entity()
        deleted.is_deleted = True
        connector2 = FakeConnector("test", [deleted])
        engine2 = SyncEngine(
            db=db,
            vector_store=mock_vector_store,
            embedding_provider=mock_embedder,
            connectors=[connector2],
        )
        await engine2.sync_all()
        mock_vector_store.delete_by_parent.assert_called()

    @pytest.mark.asyncio
    async def test_sync_state_persisted(self, db, mock_embedder, mock_vector_store):
        connector = FakeConnector("test_source", [make_entity()])
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
        """Entities with no title and no fields should be skipped, not crash the sync."""
        malformed = make_entity(id="bad:001", title="", fields=[])
        good = make_entity(id="good:001")
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
