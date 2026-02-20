"""OpenAI embedding provider using text-embedding-3-small."""

from __future__ import annotations

import logging

from openai import AsyncOpenAI

from research_agent.embedding.base import EmbeddingProvider

logger = logging.getLogger(__name__)

DIMENSIONS = {
    "text-embedding-3-small": 1536,
    "text-embedding-3-large": 3072,
    "text-embedding-ada-002": 1536,
}

MAX_BATCH_SIZE = 2048


class OpenAIEmbeddingProvider(EmbeddingProvider):
    def __init__(self, api_key: str, model: str = "text-embedding-3-small") -> None:
        self._client = AsyncOpenAI(api_key=api_key)
        self._model = model
        self._dimension = DIMENSIONS.get(model, 1536)

    def dimension(self) -> int:
        return self._dimension

    async def embed(self, text: str) -> list[float]:
        text = text.replace("\n", " ").strip()
        if not text:
            return [0.0] * self._dimension
        response = await self._client.embeddings.create(input=[text], model=self._model)
        return response.data[0].embedding

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        cleaned = [t.replace("\n", " ").strip() for t in texts]
        results: list[list[float]] = []

        for i in range(0, len(cleaned), MAX_BATCH_SIZE):
            batch = cleaned[i : i + MAX_BATCH_SIZE]
            non_empty_indices = [j for j, t in enumerate(batch) if t]
            non_empty_texts = [batch[j] for j in non_empty_indices]

            if non_empty_texts:
                response = await self._client.embeddings.create(
                    input=non_empty_texts, model=self._model
                )
                embeddings_map: dict[int, list[float]] = {}
                for idx, emb_idx in enumerate(non_empty_indices):
                    embeddings_map[emb_idx] = response.data[idx].embedding

            batch_results: list[list[float]] = []
            for j in range(len(batch)):
                if j in embeddings_map:
                    batch_results.append(embeddings_map[j])
                else:
                    batch_results.append([0.0] * self._dimension)
            results.extend(batch_results)

        return results
