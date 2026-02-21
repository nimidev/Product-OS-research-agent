"""Shared test fixtures."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock

import pytest

from research_agent.embedding.base import EmbeddingProvider
from research_agent.storage.db import Database
from research_agent.storage.models import (
    Entity,
    EntityField,
    EntityType,
    SourceSystem,
)


class MockEmbeddingProvider(EmbeddingProvider):
    """Deterministic mock that returns hash-based vectors for testing."""

    def __init__(self, dim: int = 128) -> None:
        self._dim = dim

    def dimension(self) -> int:
        return self._dim

    async def embed(self, text: str) -> list[float]:
        import hashlib
        h = hashlib.sha256(text.encode()).digest()
        vec = [float(b) / 255.0 for b in h]
        while len(vec) < self._dim:
            vec.extend(vec)
        return vec[: self._dim]

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [await self.embed(t) for t in texts]


@pytest.fixture
def mock_embedder() -> MockEmbeddingProvider:
    return MockEmbeddingProvider(dim=128)


@pytest.fixture
async def db(tmp_path):  # type: ignore[no-untyped-def]
    database = Database(db_path=str(tmp_path / "test.db"))
    await database.init()
    yield database
    await database.close()


def make_entity(
    id: str = "mock:feature_request:001",
    title: str = "Add dark mode",
    entity_type: EntityType = EntityType.FEATURE_REQUEST,
    source: SourceSystem = SourceSystem.MOCK,
    fields: list[EntityField] | None = None,
    **kwargs: Any,
) -> Entity:
    if fields is None:
        fields = [
            EntityField(field_name="title", field_type="text", field_value=title),
            EntityField(field_name="description", field_type="text", field_value="Users want a dark mode option."),
        ]
    defaults: dict[str, Any] = {
        "source_id": id.split(":")[-1] if ":" in id else id,
        "created_at": datetime(2025, 6, 15, tzinfo=timezone.utc),
        "updated_at": datetime(2025, 6, 15, tzinfo=timezone.utc),
    }
    defaults.update(kwargs)
    return Entity(
        id=id,
        entity_type=entity_type,
        source_system=source,
        title=title,
        fields=fields,
        chunks=[],
        **defaults,
    )
