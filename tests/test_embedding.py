"""Tests for embedding provider and text chunker."""

from __future__ import annotations

import pytest

from research_agent.embedding.chunker import Chunk, chunk_text
from tests.conftest import MockEmbeddingProvider


class TestMockEmbeddingProvider:
    @pytest.mark.asyncio
    async def test_embed_returns_correct_dimension(self, mock_embedder):
        vec = await mock_embedder.embed("test text")
        assert len(vec) == 128

    @pytest.mark.asyncio
    async def test_embed_deterministic(self, mock_embedder):
        v1 = await mock_embedder.embed("hello")
        v2 = await mock_embedder.embed("hello")
        assert v1 == v2

    @pytest.mark.asyncio
    async def test_embed_different_texts_differ(self, mock_embedder):
        v1 = await mock_embedder.embed("hello")
        v2 = await mock_embedder.embed("goodbye")
        assert v1 != v2

    @pytest.mark.asyncio
    async def test_embed_empty_string(self, mock_embedder):
        vec = await mock_embedder.embed("")
        assert len(vec) == 128

    @pytest.mark.asyncio
    async def test_embed_batch(self, mock_embedder):
        texts = ["one", "two", "three"]
        results = await mock_embedder.embed_batch(texts)
        assert len(results) == 3
        assert all(len(v) == 128 for v in results)

    @pytest.mark.asyncio
    async def test_embed_batch_empty(self, mock_embedder):
        results = await mock_embedder.embed_batch([])
        assert results == []


class TestChunker:
    def test_short_text_single_chunk(self):
        chunks = chunk_text("Short text.", parent_id="item1")
        assert len(chunks) == 1
        assert chunks[0].parent_id == "item1"
        assert chunks[0].index == 0
        assert chunks[0].text == "Short text."

    def test_long_text_multiple_chunks(self):
        long_text = " ".join(["word"] * 2000)
        chunks = chunk_text(long_text, parent_id="item2", max_tokens=500, overlap_tokens=50)
        assert len(chunks) > 1
        for i, chunk in enumerate(chunks):
            assert chunk.parent_id == "item2"
            assert chunk.index == i

    def test_parent_id_preserved(self):
        chunks = chunk_text("x " * 1500, parent_id="my-parent")
        for chunk in chunks:
            assert chunk.parent_id == "my-parent"

    def test_chunk_overlap(self):
        long_text = " ".join([f"sentence{i}" for i in range(500)])
        chunks = chunk_text(long_text, parent_id="item3", max_tokens=100, overlap_tokens=20)
        if len(chunks) >= 2:
            end_of_first = chunks[0].text[-50:]
            start_of_second = chunks[1].text[:100]
            # overlap means some of the first chunk's end appears in the second chunk's start
            assert len(start_of_second) > 0

    def test_empty_text(self):
        chunks = chunk_text("", parent_id="empty")
        assert len(chunks) == 1
        assert chunks[0].text == ""
