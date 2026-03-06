"""Tests for memory service."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from research_agent.memory.memory_service import MemoryService, MemorySearchResult
from research_agent.storage.models import EntityType, SourceSystem
from research_agent.vector.qdrant_client import SearchResult
from tests.conftest import MockEmbeddingProvider, make_entity


@pytest.fixture
def mock_vector_store():
    store = AsyncMock()
    store.search = AsyncMock(return_value=[])
    store.upsert = AsyncMock()
    store.upsert_batch = AsyncMock()
    store.delete_by_parent = AsyncMock()
    return store


@pytest.fixture
def mock_summarizer():
    from research_agent.synthesis.summarizer import SynthesisResult, Reference

    summarizer = AsyncMock()
    summarizer.synthesize = AsyncMock(
        return_value=SynthesisResult(
            summary="Test summary",
            references=[],
            raw_results=[],
        )
    )
    return summarizer


@pytest.fixture
async def memory_service(db, mock_embedder, mock_vector_store, mock_summarizer):
    return MemoryService(
        db=db,
        vector_store=mock_vector_store,
        embedding_provider=mock_embedder,
        summarizer=mock_summarizer,
    )


class TestMemoryServiceSearch:
    @pytest.mark.asyncio
    async def test_search_empty_results(self, memory_service):
        result = await memory_service.search_memories("test query")
        # No vector results → summarizer gets empty list → returns degraded
        assert isinstance(result.raw_results, list)
        assert len(result.raw_results) == 0

    @pytest.mark.asyncio
    async def test_search_with_results(self, db, mock_embedder, mock_summarizer):
        store = AsyncMock()
        store.search = AsyncMock(
            return_value=[
                SearchResult(
                    id="item1",
                    parent_id="item1",
                    score=0.95,
                    payload={
                        "title": "Feature A",
                        "body": "Details about feature A",
                        "source": "mock",
                        "entity_type": "feature_request",
                        "field_name": "description",
                        "metadata": {"tags": ["ui"]},
                        "created_at": "2025-06-15T00:00:00+00:00",
                    },
                )
            ]
        )
        svc = MemoryService(
            db=db,
            vector_store=store,
            embedding_provider=mock_embedder,
            summarizer=mock_summarizer,
        )
        result = await svc.search_memories("features")
        assert mock_summarizer.synthesize.called

    @pytest.mark.asyncio
    async def test_search_without_summarizer(self, db, mock_embedder):
        store = AsyncMock()
        store.search = AsyncMock(
            return_value=[
                SearchResult(
                    id="item1",
                    parent_id="item1",
                    score=0.9,
                    payload={"title": "X", "body": "Y", "source": "mock", "entity_type": "bug",
                             "field_name": "description", "metadata": {}, "created_at": ""},
                )
            ]
        )
        svc = MemoryService(
            db=db, vector_store=store, embedding_provider=mock_embedder, summarizer=None
        )
        result = await svc.search_memories("test")
        assert result.degraded is True
        assert len(result.raw_results) == 1

    @pytest.mark.asyncio
    async def test_search_with_filters(self, memory_service, mock_vector_store):
        await memory_service.search_memories(
            "bugs", source="mock", entity_types=["bug"], top_k=5
        )
        mock_vector_store.search.assert_called_once()
        call_kwargs = mock_vector_store.search.call_args[1]
        assert call_kwargs["source"] == "mock"
        assert call_kwargs["entity_types"] == ["bug"]
        assert call_kwargs["top_k"] == 5


class TestMemoryServiceAddUpdate:
    @pytest.mark.asyncio
    async def test_add_entity(self, memory_service, mock_vector_store):
        entity = make_entity()
        changed = await memory_service.add_or_update_entity(entity)
        assert changed is True

    @pytest.mark.asyncio
    async def test_add_same_entity_no_change(self, memory_service, mock_vector_store):
        entity = make_entity()
        await memory_service.add_or_update_entity(entity)
        changed = await memory_service.add_or_update_entity(entity)
        assert changed is False

    @pytest.mark.asyncio
    async def test_deleted_entity_removes_vectors(self, memory_service, mock_vector_store):
        entity = make_entity()
        await memory_service.add_or_update_entity(entity)

        deleted_entity = make_entity(is_deleted=True)
        changed = await memory_service.add_or_update_entity(deleted_entity)
        assert changed is True
        mock_vector_store.delete_by_parent.assert_called()


class TestEnrichRawResultsJiraUrl:
    """Jira search results get browse URL when site_url is in config."""

    @pytest.mark.asyncio
    async def test_jira_result_gets_browse_url_when_site_url_configured(self, db):
        db.get_integration_config = AsyncMock(
            side_effect=lambda s: (
                {
                    "source": "jira",
                    "enabled": True,
                    "api_key": "x",
                    "board_ids": [],
                    "entity_mappings": {},
                    "entity_configs": {},
                    "sync_interval_seconds": 7200,
                    "subdomain": "c1",
                    "site_url": "https://my.atlassian.net",
                }
                if s == "jira"
                else None
            )
        )
        jira_entity = make_entity(
            id="jira:KAN-42",
            title="Add SSO",
            entity_type=EntityType.ROADMAP_ITEM,
            source=SourceSystem.JIRA,
        )
        jira_entity.source_id = "KAN-42"
        db.get_entity = AsyncMock(return_value=jira_entity)

        store = AsyncMock()
        store.search = AsyncMock(return_value=[])
        svc = MemoryService(
            db=db,
            vector_store=store,
            embedding_provider=MockEmbeddingProvider(),
            summarizer=None,
        )
        raw = [
            {
                "id": "jira:KAN-42",
                "score": 0.9,
                "source": "jira",
                "title": "Add SSO",
                "body": "Desc",
                "entity_type": "roadmap_item",
                "field_name": "description",
                "metadata": {},
                "created_at": "",
            }
        ]
        enriched = await svc._enrich_raw_results(raw)
        assert len(enriched) == 1
        assert enriched[0].get("url") == "https://my.atlassian.net/browse/KAN-42"

    @pytest.mark.asyncio
    async def test_jira_result_no_url_when_site_url_missing(self, db):
        db.get_integration_config = AsyncMock(
            return_value={
                "source": "jira",
                "enabled": True,
                "api_key": "x",
                "subdomain": "c1",
                "site_url": None,
                "board_ids": [],
                "entity_mappings": {},
                "entity_configs": {},
                "sync_interval_seconds": 7200,
            }
        )
        jira_entity = make_entity(
            id="jira:KAN-1",
            title="Bug",
            entity_type=EntityType.BUG,
            source=SourceSystem.JIRA,
        )
        jira_entity.source_id = "KAN-1"
        db.get_entity = AsyncMock(return_value=jira_entity)

        store = AsyncMock()
        store.search = AsyncMock(return_value=[])
        svc = MemoryService(
            db=db,
            vector_store=store,
            embedding_provider=MockEmbeddingProvider(),
            summarizer=None,
        )
        raw = [
            {
                "id": "jira:KAN-1",
                "score": 0.8,
                "source": "jira",
                "title": "Bug",
                "body": "Desc",
                "entity_type": "bug",
                "field_name": "description",
                "metadata": {},
                "created_at": "",
            }
        ]
        enriched = await svc._enrich_raw_results(raw)
        assert len(enriched) == 1
        assert enriched[0].get("url") == ""
