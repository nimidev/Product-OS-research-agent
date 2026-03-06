"""Core memory service — search (with field-aware + flexible scope) and add/update entities."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import httpx

from research_agent.embedding.base import EmbeddingProvider
from research_agent.embedding.chunker import chunk_text
from research_agent.storage.db import Database
from research_agent.storage.models import Entity
from research_agent.synthesis.summarizer import Summarizer, SynthesisResult
from research_agent.vector.qdrant_client import QdrantStore, SearchResult

from research_agent.memory.query_understanding import infer_entity_scope

logger = logging.getLogger(__name__)

SEARCHABLE_FIELDS = {
    "title",
    "description",
    "transcript",
    "overview",
    "summary",
    "requirements",
    "success_metrics",
}


@dataclass
class MemorySearchResult:
    summary: str
    references: list[dict[str, Any]]
    raw_results: list[dict[str, Any]]
    degraded: bool = False


@dataclass
class ResearchPlan:
    """Planned search scope + depth for a given question."""

    question_type: str  # lookup | diagnostic | strategy | exploratory
    depth: str  # simple | deep
    entity_types: list[str] | None
    field_names: list[str] | None
    top_k: int


def _search_result_to_dict(sr: SearchResult) -> dict[str, Any]:
    payload = sr.payload
    return {
        "id": sr.parent_id,
        "score": sr.score,
        "title": payload.get("title", ""),
        "body": payload.get("body", ""),
        "source": payload.get("source", ""),
        "type": payload.get("entity_type", payload.get("type", "")),
        "entity_type": payload.get("entity_type", ""),
        "field_name": payload.get("field_name", ""),
        "metadata": payload.get("metadata", {}),
        "created_at": payload.get("created_at", ""),
    }


def _entity_to_enriched_dict(entity: Entity, base: dict[str, Any], url: str = "") -> dict[str, Any]:
    """Merge all entity fields into search result dict so synthesis has full context (description, votes, etc.)."""
    field_map = {f.field_name: (f.field_value or "").strip() for f in entity.fields}
    out = {
        **base,
        "title": entity.title,
        "description": field_map.get("description", ""),
        "votes": field_map.get("votes", ""),
        "status": field_map.get("status", ""),
        "customer": field_map.get("customer", ""),
        "priority": field_map.get("priority", ""),
        "url": url,
    }
    for name, value in field_map.items():
        if name not in out or not out[name]:
            out[name] = value
    if url:
        out["metadata"] = {**(base.get("metadata") or {}), "url": url}
    return out


def _classify_question(query: str) -> tuple[str, str]:
    """Heuristic classification of question type and expected depth.

    This does not affect semantics of answers, only how broad/deep we search.
    """
    text = (query or "").lower().strip()
    if not text:
        return "lookup", "simple"

    # Strategy / recommendation
    if any(
        kw in text
        for kw in (
            "what should we do",
            "what should we prioritize",
            "how should we respond",
            "recommendation",
            "recommendations",
            "strategy",
        )
    ):
        return "strategy", "deep"

    # Diagnostic / what's going wrong
    if any(
        kw in text
        for kw in (
            "why ",
            "what's going wrong",
            "what is going wrong",
            "issues",
            "problems",
            "blocking",
            "blocked",
        )
    ):
        return "diagnostic", "deep"

    # Research / synthesis
    if any(
        kw in text
        for kw in (
            "summarize everything we know",
            "summarise everything we know",
            "summarize",
            "overview",
            "deep research",
            "synthesis",
        )
    ):
        return "exploratory", "deep"

    # Simple lookup / counts / where-do-we-mention
    if any(
        kw in text
        for kw in (
            "how many ",
            "how much ",
            "count ",
            "number of ",
            "list of ",
            "where do we mention",
            "where do we reference",
        )
    ):
        return "lookup", "simple"

    # Fallback: short questions → lookup, longer → exploratory
    if len(text.split()) <= 6:
        return "lookup", "simple"
    return "exploratory", "deep"


def _plan_research(
    query: str,
    context: str | None,
    top_k: int,
    entity_types: list[str] | None,
    field_names: list[str] | None,
    use_query_understanding: bool,
) -> ResearchPlan:
    """Build a simple research plan: question type, depth, scope, and top_k.

    This encodes the AC3 playbook at the retrieval level:
    - interpret question type / depth
    - resolve entity types / fields (including inference when allowed)
    - decide how broadly to search (top_k)
    """
    question_type, depth = _classify_question(query)

    resolved_entity_types = entity_types
    resolved_field_names = field_names

    # If caller did not explicitly scope, optionally infer from query/context
    if use_query_understanding and resolved_entity_types is None and resolved_field_names is None:
        inferred_types, inferred_fields = infer_entity_scope(query, context)
        if inferred_types:
            resolved_entity_types = inferred_types
        if inferred_fields:
            resolved_field_names = inferred_fields

    # For deeper research, ensure we look across multiple entity types.
    # If nothing was resolved, use a broad default set.
    deep_default_entity_types = [
        "feature_request",
        "bug",
        "support_ticket",
        "prd",
        "roadmap_item",
        "meeting_note",
    ]
    if question_type in {"diagnostic", "strategy", "exploratory"}:
        if not resolved_entity_types:
            resolved_entity_types = deep_default_entity_types
        else:
            # Union of inferred/explicit types and the default deep set
            resolved_entity_types = list(
                dict.fromkeys(list(resolved_entity_types) + deep_default_entity_types)
            )

    # Tune top_k by depth: keep lookups light, research deeper
    if question_type == "lookup" and depth == "simple":
        planned_top_k = min(top_k, 10)
    else:
        planned_top_k = max(top_k, 20)

    return ResearchPlan(
        question_type=question_type,
        depth=depth,
        entity_types=resolved_entity_types,
        field_names=resolved_field_names,
        top_k=planned_top_k,
    )


class MemoryService:
    def __init__(
        self,
        db: Database,
        vector_store: QdrantStore,
        embedding_provider: EmbeddingProvider,
        summarizer: Summarizer | None = None,
    ) -> None:
        self._db = db
        self._vector = vector_store
        self._embedder = embedding_provider
        self._summarizer = summarizer

    @staticmethod
    def _build_context_aware_query(query: str, context: str | None) -> str:
        if not context:
            return query
        return f"Previous research context:\n{context}\n\nCurrent question: {query}"

    async def _enrich_raw_results(self, raw_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Dedupe by entity id (keep best score), load full entity from DB, add description/votes/status/url."""
        if not raw_results:
            return raw_results
        # Dedupe by id, keeping highest score
        by_id: dict[str, dict[str, Any]] = {}
        for r in raw_results:
            eid = r.get("id") or ""
            if eid and (eid not in by_id or (r.get("score") or 0) > (by_id[eid].get("score") or 0)):
                by_id[eid] = r
        # Monday board_id + subdomain for URL (tenant-specific: https://{subdomain}.monday.com/...)
        monday_board_id: str | None = None
        monday_subdomain: str = "app"
        if any(r.get("source") == "monday" for r in by_id.values()):
            cfg = await self._db.get_integration_config("monday")
            if cfg:
                if cfg.get("board_ids"):
                    monday_board_id = str(cfg["board_ids"][0])
                sub = (cfg.get("subdomain") or "").strip()
                if sub:
                    monday_subdomain = sub
        # Jira site base URL for browse links (https://your-site.atlassian.net/browse/KEY)
        jira_site_base: str | None = None
        if any(r.get("source") == "jira" for r in by_id.values()):
            jira_cfg = await self._db.get_integration_config("jira")
            if jira_cfg:
                base = (jira_cfg.get("site_url") or "").strip().rstrip("/")
                if base:
                    jira_site_base = base
                elif (jira_cfg.get("api_key") or "").strip() and (jira_cfg.get("subdomain") or "").strip():
                    # Backfill: resolve site URL from Atlassian accessible-resources (e.g. config from before site_url was stored)
                    try:
                        async with httpx.AsyncClient(timeout=10.0) as client:
                            resp = await client.get(
                                "https://api.atlassian.com/oauth/token/accessible-resources",
                                headers={
                                    "Authorization": f"Bearer {jira_cfg['api_key'].strip()}",
                                    "Accept": "application/json",
                                },
                            )
                            if resp.status_code == 200:
                                resources = resp.json()
                                cloud_id = (jira_cfg.get("subdomain") or "").strip()
                                for r in (resources or []):
                                    if (r.get("id") or "").strip() == cloud_id:
                                        base = (r.get("url") or "").strip().rstrip("/")
                                        if base:
                                            jira_site_base = base
                                            # Persist so future requests don't need to call the API
                                            await self._db.upsert_integration_config(
                                                source="jira",
                                                enabled=bool(jira_cfg.get("enabled")),
                                                board_ids=jira_cfg.get("board_ids") or [],
                                                entity_mappings=jira_cfg.get("entity_mappings") or {},
                                                sync_interval_seconds=int(jira_cfg.get("sync_interval_seconds", 7200)),
                                                api_key=jira_cfg.get("api_key"),
                                                entity_configs=jira_cfg.get("entity_configs"),
                                                subdomain=jira_cfg.get("subdomain"),
                                                oauth_client_id=jira_cfg.get("oauth_client_id"),
                                                oauth_client_secret=jira_cfg.get("oauth_client_secret"),
                                                site_url=base,
                                            )
                                        break
                    except Exception as e:
                        logger.warning("Jira site_url backfill from accessible-resources failed: %s", e)
        enriched: list[dict[str, Any]] = []
        for eid, base in by_id.items():
            entity = await self._db.get_entity(eid)
            url = ""
            if base.get("source") == "monday" and monday_board_id and eid.startswith("monday:"):
                pulse_id = eid.split(":", 1)[1]
                url = f"https://{monday_subdomain}.monday.com/boards/{monday_board_id}/pulses/{pulse_id}"
            elif base.get("source") == "jira" and jira_site_base and eid.startswith("jira:"):
                issue_key = eid.split(":", 1)[1] if ":" in eid else (entity.source_id if entity else "")
                if issue_key:
                    url = f"{jira_site_base}/browse/{issue_key}"
            if entity:
                enriched.append(_entity_to_enriched_dict(entity, base, url))
            else:
                base["url"] = url
                if url:
                    base["metadata"] = {**(base.get("metadata") or {}), "url": url}
                enriched.append(base)
        # Restore order by score desc
        enriched.sort(key=lambda x: -(x.get("score") or 0))
        return enriched

    async def search_memories(
        self,
        query: str,
        top_k: int = 10,
        entity_types: list[str] | None = None,
        field_names: list[str] | None = None,
        source: str | None = None,
        allowed_sources: list[str] | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        tags: list[str] | None = None,
        context: str | None = None,
        use_query_understanding: bool = True,
    ) -> MemorySearchResult:
        """Search with optional entity/field scope. When entity_types/field_names are
        omitted or empty, infers scope from query + context if use_query_understanding
        is True; otherwise searches all.
        """
        # 1) Plan research scope and depth (question type, entities, top_k)
        plan = _plan_research(
            query=query,
            context=context,
            top_k=top_k,
            entity_types=entity_types,
            field_names=field_names,
            use_query_understanding=use_query_understanding,
        )

        # 2) Embed query (with conversational context woven in)
        search_query = self._build_context_aware_query(query, context)
        query_vector = await self._embedder.embed(search_query)

        # When any integration is active, restrict to allowed_sources only (excludes mock)
        source_filter = source
        sources_filter: list[str] | None = None
        if allowed_sources:
            sources_filter = allowed_sources
            if source and source not in allowed_sources:
                source_filter = None
        results = await self._vector.search(
            query_vector=query_vector,
            top_k=plan.top_k,
            source=source_filter,
            sources=sources_filter,
            entity_types=plan.entity_types,
            field_names=plan.field_names,
            date_from=date_from,
            date_to=date_to,
            tags=tags,
        )

        raw_results = [_search_result_to_dict(r) for r in results]
        raw_results = await self._enrich_raw_results(raw_results)

        total_count: int | None = None
        if plan.entity_types or source or allowed_sources:
            total_count = await self._db.count_entities(
                entity_type=plan.entity_types[0] if (plan.entity_types and len(plan.entity_types) > 0) else None,
                source_system=source if not allowed_sources else None,
                source_systems=allowed_sources,
            )

        if not raw_results:
            return MemorySearchResult(
                summary="No results found for this query. Try a different search or check that your integration data is synced.",
                references=[],
                raw_results=[],
                degraded=False,
            )

        if self._summarizer:
            synthesis = await self._summarizer.synthesize(
                query, raw_results, context, total_count=total_count
            )
            return MemorySearchResult(
                summary=synthesis.summary,
                references=[
                    {
                        "title": ref.title,
                        "url": ref.url,
                        "source": ref.source,
                        "type": ref.type,
                        "index": ref.index,
                        "typed_id": ref.typed_id,
                        "entity_type": ref.entity_type,
                        "entity_id": ref.entity_id,
                    }
                    for ref in synthesis.references
                ],
                raw_results=raw_results,
                degraded=synthesis.degraded,
            )

        return MemorySearchResult(
            summary="Synthesis unavailable. Raw results provided.",
            references=[],
            raw_results=raw_results,
            degraded=True,
        )

    async def add_or_update_entity(self, entity: Entity) -> bool:
        """Upsert entity to SQLite and embed + upsert chunks to Qdrant. Returns True if changed."""
        from research_agent.storage.models import Chunk as StorageChunk

        changed = await self._db.upsert_entity(entity)
        if not changed:
            return False

        await self._vector.delete_by_parent(entity.id)

        if entity.is_deleted:
            return True

        chunks_list: list[StorageChunk] = []
        for f in entity.fields:
            if f.field_name not in SEARCHABLE_FIELDS or not f.field_value or not f.field_value.strip():
                continue
            for c in chunk_text(f.field_value, parent_id=entity.id):
                chunks_list.append(
                    StorageChunk(
                        id=f"{entity.id}:{f.field_name}:{c.index}",
                        field_name=f.field_name,
                        chunk_index=c.index,
                        text=c.text,
                    )
                )

        if chunks_list:
            texts = [c.text for c in chunks_list]
            vectors = await self._embedder.embed_batch(texts)
            points = [
                (
                    c.id,
                    vec,
                    {
                        "parent_id": entity.id,
                        "entity_type": entity.entity_type.value,
                        "field_name": c.field_name,
                        "title": entity.title,
                        "source": entity.source_system.value,
                        "body": c.text[:2000],
                        "chunk_index": c.chunk_index,
                        "created_at": entity.created_at.isoformat() if entity.created_at else "",
                        "updated_at": entity.updated_at.isoformat() if entity.updated_at else "",
                    },
                )
                for c, vec in zip(chunks_list, vectors, strict=True)
            ]
            await self._vector.upsert_batch(points)

        return True
