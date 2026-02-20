"""Abstract embedding provider interface."""

from __future__ import annotations

from abc import ABC, abstractmethod


class EmbeddingProvider(ABC):
    """Contract for any embedding backend (OpenAI, local, etc.)."""

    @abstractmethod
    async def embed(self, text: str) -> list[float]:
        """Return the embedding vector for a single text."""

    @abstractmethod
    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Return embedding vectors for a batch of texts."""

    @abstractmethod
    def dimension(self) -> int:
        """Return the dimensionality of the embedding vectors."""
