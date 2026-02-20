"""Tests for AI synthesis / summarizer."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from research_agent.synthesis.summarizer import (
    Summarizer,
    SynthesisResult,
    _build_results_context,
    _extract_cited_indices,
)


class TestHelpers:
    def test_extract_cited_indices(self):
        text = "Based on [1] and [3], the feature is popular. See also [1]."
        indices = _extract_cited_indices(text)
        assert indices == {1, 3}

    def test_extract_no_citations(self):
        assert _extract_cited_indices("No citations here.") == set()

    def test_build_results_context(self):
        results = [
            {
                "title": "Feature A",
                "source": "mock",
                "type": "feature_request",
                "body": "Details",
                "metadata": {"tags": ["ui"]},
            }
        ]
        ctx = _build_results_context(results)
        assert "[1]" in ctx
        assert "Feature A" in ctx
        assert "mock/feature_request" in ctx


class TestSummarizer:
    @pytest.mark.asyncio
    async def test_empty_results(self):
        summarizer = Summarizer(api_key="fake", model="gpt-4o-mini")
        result = await summarizer.synthesize("query", [])
        assert result.summary == "No results found for this query."
        assert result.references == []
        assert result.raw_results == []
        assert result.degraded is False

    @pytest.mark.asyncio
    async def test_llm_failure_returns_degraded(self):
        summarizer = Summarizer(api_key="fake", model="gpt-4o-mini")
        summarizer._call_llm = AsyncMock(side_effect=Exception("API error"))

        results = [{"title": "A", "body": "B", "source": "mock", "type": "bug", "metadata": {}}]
        result = await summarizer.synthesize("query", results)
        assert result.degraded is True
        assert len(result.raw_results) == 1

    @pytest.mark.asyncio
    async def test_synthesis_with_mocked_llm(self):
        summarizer = Summarizer(api_key="fake", model="gpt-4o-mini")

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = (
            "The main issue is performance [1]. Users also want dark mode [2]."
        )

        summarizer._client = AsyncMock()
        summarizer._client.chat = MagicMock()
        summarizer._client.chat.completions = MagicMock()
        summarizer._client.chat.completions.create = AsyncMock(return_value=mock_response)

        results = [
            {"title": "Perf issue", "body": "Slow", "source": "mock",
             "type": "bug", "metadata": {"url": "http://a"}},
            {"title": "Dark mode", "body": "Want it", "source": "mock",
             "type": "feature_request", "metadata": {"url": "http://b"}},
        ]

        result = await summarizer.synthesize("what are users saying?", results)
        assert "[1]" in result.summary
        assert "[2]" in result.summary
        assert len(result.references) == 2
        assert result.references[0].title == "Perf issue"
        assert result.references[1].title == "Dark mode"
        assert result.degraded is False
