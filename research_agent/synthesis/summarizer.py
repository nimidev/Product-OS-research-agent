"""LLM-powered synthesis: search results → summary with citations."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

from openai import AsyncOpenAI

logger = logging.getLogger(__name__)


@dataclass
class Reference:
    title: str
    url: str
    source: str
    type: str


@dataclass
class SynthesisResult:
    summary: str
    references: list[Reference]
    raw_results: list[dict[str, Any]]
    degraded: bool = False


SYSTEM_PROMPT = """\
You are a research assistant that synthesizes organizational knowledge.
Given a user query and search results from the knowledge base, produce a clear,
concise summary that directly answers the query.

Rules:
- Cite sources using [n] notation where n is the 1-based index in the results list.
- Only cite sources that appear in the provided results. Never invent references.
- If results are insufficient, say so honestly.
- Be concise — aim for 3-8 sentences unless the query demands more detail.
- Group related findings together.
- Highlight key themes, patterns, and contradictions.
"""


def _build_results_context(results: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for i, r in enumerate(results, 1):
        title = r.get("title", "Untitled")
        source = r.get("source", "unknown")
        item_type = r.get("type", "unknown")
        body = r.get("body", "")[:1000]
        metadata = r.get("metadata", {})
        tags = metadata.get("tags", [])
        lines.append(
            f"[{i}] ({source}/{item_type}) {title}\n"
            f"Tags: {', '.join(tags) if tags else 'none'}\n"
            f"{body}\n"
        )
    return "\n---\n".join(lines)


def _extract_cited_indices(summary: str) -> set[int]:
    """Parse [n] citation markers from the summary text."""
    import re

    return {int(m) for m in re.findall(r"\[(\d+)\]", summary)}


class Summarizer:
    def __init__(self, api_key: str, model: str = "gpt-4o-mini") -> None:
        self._client = AsyncOpenAI(api_key=api_key)
        self._model = model

    async def synthesize(
        self,
        query: str,
        results: list[dict[str, Any]],
        context: str | None = None,
    ) -> SynthesisResult:
        if not results:
            return SynthesisResult(
                summary="No results found for this query.",
                references=[],
                raw_results=results,
            )

        try:
            return await self._call_llm(query, results, context)
        except Exception:
            logger.exception("LLM synthesis failed, returning raw results in degraded mode")
            return SynthesisResult(
                summary="Synthesis unavailable. Raw results provided below.",
                references=[],
                raw_results=results,
                degraded=True,
            )

    async def _call_llm(
        self,
        query: str,
        results: list[dict[str, Any]],
        context: str | None = None,
    ) -> SynthesisResult:
        results_text = _build_results_context(results)
        user_content = f"Query: {query}\n\n"
        if context:
            user_content += f"Previous conversation context:\n{context}\n\n"
        user_content += f"Search results:\n{results_text}"

        response = await self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            temperature=0.3,
            max_tokens=1500,
        )

        summary = response.choices[0].message.content or ""

        cited = _extract_cited_indices(summary)
        references: list[Reference] = []
        for idx in sorted(cited):
            if 1 <= idx <= len(results):
                r = results[idx - 1]
                metadata = r.get("metadata", {})
                references.append(
                    Reference(
                        title=r.get("title", "Untitled"),
                        url=metadata.get("url", ""),
                        source=r.get("source", "unknown"),
                        type=r.get("type", "unknown"),
                    )
                )

        return SynthesisResult(
            summary=summary,
            references=references,
            raw_results=results,
        )
