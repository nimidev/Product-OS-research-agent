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
    # 1-based index in the synthesized results list, matching [n] markers in the summary.
    index: int | None = None
    # Short, answer-local typed ID (e.g. BUG-8, FR-3) derived from entity_type + index.
    typed_id: str | None = None
    # Canonical entity type (e.g. feature_request, bug, support_ticket).
    entity_type: str | None = None
    # Canonical entity id in the underlying store, when available.
    entity_id: str | None = None


@dataclass
class SynthesisResult:
    summary: str
    references: list[Reference]
    raw_results: list[dict[str, Any]]
    degraded: bool = False


SYSTEM_PROMPT = """\
You are a senior product researcher for a SaaS organization.
You answer product questions by synthesizing **only** the provided organizational search results.

Your goals:
- Give product managers a clear bottom line.
- Surface non-obvious, cross-entity insights (e.g. patterns across feature requests, bugs, support, roadmap, PRDs, meeting notes).
- Be honest and direct about problems, risks, and data gaps.

General rules:
- **Grounding only:** Use only the provided search results as evidence. Never invent entities, metrics, or events.
- **Citations:** Cite sources using [n] where n is the 1-based index in the results list.
- **Formatting:** Use Markdown. Use **bold** for item titles and field labels (e.g. **Description:**, **Votes:**).
  - Use numbered lists (1. 2. 3.) or bullets (-) for lists; put a blank line between items.
- **Totals:** When a \"Total matching items\" count is given, mention it early (e.g. \"There are N matching items; below are the top M results:\").
- **No fake gaps:** Do NOT say \"votes are not included\", \"descriptions are not available\", or \"limited information\" if those fields actually appear in the results. Only say data is missing when the field is empty or absent.
- **Tone:** Be concise and straightforward. Avoid filler, apologies, or generic PM theory unless the user explicitly asks for it.

Dynamic response structure (AC1):
1. **Simple lookup questions** (counts, fact retrieval, \"where do we mention X\", \"what did we decide about Y\"):
   - Return a **short, direct answer** (1–3 sentences) plus minimal context.
   - Do NOT force a full multi-section layout.

2. **Research / diagnostic / strategy questions** (\"what's going wrong\", \"how is X performing\", \"what should we do\", \"summarize everything we know about X\"):
   - Use a structured format, with some or all of:
     - **TL;DR** – 1–3 sentences, the main conclusion(s).
     - **Key insights** – bullets that summarize the most important findings.
     - **Evidence / data sources** – which entity types and examples support the insights (e.g. feature requests, bugs, support, PRDs, meeting notes, roadmap).
     - **Recommendations / next actions** – only when the question asks for guidance or it is clearly implied.
     - **Optional deep dives** – e.g. user feedback themes, usage/impact notes, or enterprise vs self-serve differences when useful.

Intent, scope, and data usage (AC2–AC4):
- Infer the question type (lookup vs diagnostic vs strategy vs exploratory) from the wording.
- Infer and make clear the relevant **scope** when possible:
  - Product/feature/topic.
  - Timeframe, if present in the results or obviously implied; otherwise do not invent dates.
- Use **multiple entity types** when available (feature requests, bugs, support, PRDs, roadmap, meeting notes, etc.) and explicitly connect signals across them:
  - Call out patterns like \"the same reliability issue shows up in feature requests, bugs, and support\".
  - Distinguish:
    - **Facts** (directly from results),
    - **Interpretations** (your analysis of those facts),
    - **Hypotheses/assumptions** (clearly labeled when data is weak or missing).

Honesty, problems, and gaps (AC5–AC7):
- Highlight real problems and risks prominently (e.g. in the TL;DR and Key insights) when the data supports them.
- It is always acceptable to say:
  - \"Data is insufficient to answer this fully\"; and briefly say what is missing.
  - \"The results do not directly address X; here is what we can infer (clearly labeled as interpretation).\" 
- When **no relevant entities** appear in the results for the user’s question, say so plainly (e.g. \"Based on the retrieved results, there are no direct items about &lt;topic&gt;\"), and do **not** invent an answer from generic product knowledge.
- Never fabricate numbers, trends, or entities. If you need to generalize, do it qualitatively and tie it back to specific cited items.

Always:
- Directly answer the user’s question.
- Respect the simple vs deep structure rules above.
- Make it easy for a PM to see:
  - The bottom line,
  - The main evidence,
  - The key problems/risks,
  - And, when appropriate, recommended next steps.
"""


# Keys we do not show as content (internal/search metadata)
_RESULT_SKIP_KEYS = frozenset({
    "id", "score", "source", "type", "entity_type", "field_name", "metadata",
    "created_at", "body", "url",
})


def _build_results_context(results: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for i, r in enumerate(results, 1):
        title = r.get("title", "Untitled")
        source = r.get("source", "unknown")
        item_type = r.get("type", "unknown")
        body = (r.get("body") or "")[:1000]
        metadata = r.get("metadata", {}) or {}
        tags = metadata.get("tags", [])
        parts = [f"[{i}] ({source}/{item_type}) {title}"]
        for k, v in sorted(r.items()):
            if k in _RESULT_SKIP_KEYS:
                continue
            if isinstance(v, str) and v.strip():
                parts.append(f"{k}: {v.strip()[:2000]}")
            elif isinstance(v, (int, float)) and k != "score":
                parts.append(f"{k}: {v}")
        if tags:
            parts.append(f"Tags: {', '.join(tags)}")
        parts.append("")
        if body:
            parts.append(body)
        lines.append("\n".join(parts))
    return "\n---\n".join(lines)


def _extract_cited_indices(summary: str) -> set[int]:
    """Parse [n] or [n, m] style citation markers from the summary text."""
    import re

    indices: set[int] = set()
    # Matches [1], [2, 3], [4, 7, 10], etc.
    for group in re.findall(r"\[([0-9,\s]+)\]", summary):
        for part in group.split(","):
            part = part.strip()
            if part.isdigit():
                indices.add(int(part))
    return indices


def _looks_like_no_results(summary: str) -> bool:
    """Heuristic check for answers that incorrectly claim there are no relevant items."""
    text = (summary or "").lower()
    patterns = [
        "no direct items",
        "no direct results",
        "no results found",
        "none specifically address",
        "none specifically about",
        "no direct evidence",
    ]
    return any(p in text for p in patterns)


def _build_no_results_fallback_summary(
    query: str,
    results: list[dict[str, Any]],
    total_count: int | None = None,
) -> str:
    """Fallback summary when the LLM incorrectly says there are no direct items.

    We still want a grounded, pattern-based answer over the returned entities.
    """
    total = total_count if total_count is not None else len(results)

    type_counts: dict[str, int] = {}
    titles: list[str] = []
    for r in results:
        et = (r.get("entity_type") or r.get("type") or "entity").lower()
        type_counts[et] = type_counts.get(et, 0) + 1
        title = (r.get("title") or r.get("body") or "").strip()
        if title:
            titles.append(title.lower())

    # crude keyword extraction from titles
    STOPWORDS = {
        "the",
        "and",
        "or",
        "to",
        "for",
        "in",
        "of",
        "a",
        "an",
        "on",
        "with",
        "mode",
        "support",
        "feature",
        "features",
        "improvements",
        "improvement",
        "app",
        "api",
        "via",
        "project",
        "projects",
    }
    freq: dict[str, int] = {}
    for t in titles:
        for tok in t.replace(":", " ").replace("-", " ").split():
            tok = tok.strip(".,!?\"'()").lower()
            if len(tok) < 4 or tok in STOPWORDS:
                continue
            freq[tok] = freq.get(tok, 0) + 1

    # pick top 3 thematic tokens as a cheap "themes" proxy
    themes = sorted(freq.items(), key=lambda kv: kv[1], reverse=True)[:3]
    theme_str = ", ".join(f"{word}" for word, _ in themes) if themes else "no clear dominant theme"

    parts: list[str] = []
    parts.append(
        f"**TL;DR:** The search returned {total} related items, mostly feature requests. "
        f"Taken together they show that users are primarily asking for things around {theme_str}."
    )
    parts.append("")
    parts.append("### Key insights")
    if type_counts:
        breakdown = ", ".join(
            f"{count} {etype.replace('_', ' ')}" for etype, count in type_counts.items()
        )
        parts.append(f"- Items span: {breakdown}.")
    if themes:
        parts.append(
            "- Repeated themes in the feature request titles include: "
            + ", ".join(f"`{w}`" for w, _ in themes)
            + "."
        )
    if not type_counts and not themes:
        parts.append(
            "- There are items in the knowledge base, but their types and titles do not reveal clear themes."
        )

    parts.append("")
    parts.append("### Evidence / data sources")
    top = results[:5]
    for i, r in enumerate(top, 1):
        title = r.get("title") or r.get("body") or "Untitled"
        etype = r.get("entity_type") or r.get("type") or "entity"
        source = r.get("source", "unknown")
        parts.append(f"- [{i}] ({source}/{etype}) {title}")

    return "\n".join(parts)


class Summarizer:
    def __init__(self, api_key: str, model: str = "gpt-4o") -> None:
        self._client = AsyncOpenAI(api_key=api_key)
        self._model = model

    async def synthesize(
        self,
        query: str,
        results: list[dict[str, Any]],
        context: str | None = None,
        total_count: int | None = None,
    ) -> SynthesisResult:
        if not results:
            return SynthesisResult(
                summary="No results found for this query.",
                references=[],
                raw_results=results,
            )

        try:
            return await self._call_llm(query, results, context, total_count=total_count)
        except Exception:
            logger.exception("LLM synthesis failed, returning raw results in degraded mode")
            return SynthesisResult(
                summary="Research unavailable right now; try again in a moment.",
                references=[],
                raw_results=results,
                degraded=True,
            )

    async def _call_llm(
        self,
        query: str,
        results: list[dict[str, Any]],
        context: str | None = None,
        total_count: int | None = None,
    ) -> SynthesisResult:
        results_text = _build_results_context(results)
        user_content = f"Query: {query}\n\n"
        if total_count is not None:
            user_content += (
                f"Total matching items in the knowledge base: {total_count}. "
                f"Below are the top {len(results)} results from semantic search.\n\n"
            )
        if context:
            user_content += f"Previous conversation context:\n{context}\n\n"

        # If search results clearly contain terms from the question, reinforce that they are relevant.
        # This discourages the model from saying "no direct items" when there is usable evidence.
        query_tokens = {t.lower() for t in query.split() if len(t) >= 4}
        if query_tokens:
            overlap = 0
            for r in results:
                haystack = " ".join(
                    [
                        str(r.get("title", "")).lower(),
                        str(r.get("description", "")).lower(),
                        str(r.get("body", "")).lower(),
                    ]
                )
                if any(t in haystack for t in query_tokens):
                    overlap += 1
            if overlap:
                user_content += (
                    "Important: The search results contain items that share key words with your question. "
                    "You MUST treat them as directly relevant evidence, and you MUST summarize what they say "
                    "instead of saying there are no direct items.\n\n"
                )

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

        # If the model incorrectly claims there are "no direct items" while we do have results,
        # replace the answer with a grounded fallback summary so the UX is never a dead-end.
        if results and _looks_like_no_results(summary):
            summary = _build_no_results_fallback_summary(query, results, total_count)

        cited = _extract_cited_indices(summary)
        references: list[Reference] = []
        for idx in sorted(cited):
            if 1 <= idx <= len(results):
                r = results[idx - 1]
                metadata = r.get("metadata", {})
                entity_type = (r.get("entity_type") or r.get("type") or "entity").lower()

                # Map canonical entity types to short prefixes for typed IDs.
                prefix_map = {
                    "feature_request": "FR",
                    "bug": "BUG",
                    "support_ticket": "SUP",
                    "prd": "PRD",
                    "roadmap_item": "RD",
                    "meeting_note": "MTG",
                }
                prefix = prefix_map.get(entity_type, (entity_type or "entity").upper())
                typed_id = f"{prefix}-{idx}"

                references.append(
                    Reference(
                        title=r.get("title", "Untitled"),
                        url=r.get("url") or metadata.get("url", ""),
                        source=r.get("source", "unknown"),
                        type=r.get("type", "unknown"),
                        index=idx,
                        typed_id=typed_id,
                        entity_type=entity_type,
                        entity_id=str(r.get("id") or ""),
                    )
                )

        return SynthesisResult(
            summary=summary,
            references=references,
            raw_results=results,
        )
