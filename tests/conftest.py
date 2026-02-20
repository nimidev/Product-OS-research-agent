"""Shared test fixtures."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock

import pytest

from research_agent.embedding.base import EmbeddingProvider
from research_agent.storage.db import Database
from research_agent.storage.models import Item, ItemSource, ItemType


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


def make_item(
    id: str = "mock:feature_request:001",
    title: str = "Add dark mode",
    body: str = "Users want a dark mode option for the app.",
    source: ItemSource = ItemSource.MOCK,
    item_type: ItemType = ItemType.FEATURE_REQUEST,
    **kwargs: Any,
) -> Item:
    defaults: dict[str, Any] = {
        "metadata": {"tags": ["ui", "theme"], "priority": "high"},
        "created_at": datetime(2025, 6, 15, tzinfo=timezone.utc),
        "updated_at": datetime(2025, 6, 15, tzinfo=timezone.utc),
    }
    defaults.update(kwargs)
    return Item(id=id, source=source, type=item_type, title=title, body=body, **defaults)
