"""FastAPI REST API — POST /search_memories, GET /health, GET /sources."""

from __future__ import annotations

import json
import logging
import time
from contextlib import asynccontextmanager
from typing import Any, Literal

import httpx
from fastapi import FastAPI, HTTPException, Request
from starlette.exceptions import HTTPException as StarletteHTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel, Field

from research_agent.config.loader import create_vector_store, get_settings
from research_agent.connectors.jira_connector import JiraConnector
from research_agent.connectors.monday_connector import MONDAY_API_URL, MondayConnector
from research_agent.embedding.openai_provider import OpenAIEmbeddingProvider
from research_agent.logging_config import configure_logging
from research_agent.memory.memory_service import MemoryService
from research_agent.storage.db import Database
from research_agent.storage.models import SourceSystem, EntityRow, EntityType, CANONICAL_FIELDS, CANONICAL_FIELD_DESCRIPTIONS
from research_agent.synthesis.summarizer import Summarizer
from research_agent.vector.qdrant_client import QdrantStore
from research_agent.sync.sync_all import SyncEngine
from research_agent.__main__ import _build_connectors

logger = logging.getLogger(__name__)

_memory_service: MemoryService | None = None
_db: Database | None = None
_vector_store: QdrantStore | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):  # type: ignore[no-untyped-def]
    global _memory_service
    global _db
    global _vector_store
    settings = get_settings()
    configure_logging(settings.log_level)

    db = Database(db_path=settings.database_path)
    await db.init()
    _db = db

    vector_store = create_vector_store(settings)
    _vector_store = vector_store
    embedding = OpenAIEmbeddingProvider(
        api_key=settings.openai_api_key, model=settings.embedding_model
    )

    try:
        await vector_store.ensure_collection(embedding.dimension())
    except Exception:
        logger.exception("Failed to connect to Qdrant — search will be unavailable")

    summarizer = (
        Summarizer(api_key=settings.openai_api_key, model=settings.llm_model)
        if settings.openai_api_key
        else None
    )

    _memory_service = MemoryService(
        db=db,
        vector_store=vector_store,
        embedding_provider=embedding,
        summarizer=summarizer,
    )

    logger.info("Research Agent API started")
    yield

    await vector_store.close()
    await db.close()
    _db = None
    logger.info("Research Agent API stopped")


app = FastAPI(
    title="Research Agent API",
    version="0.1.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Ensure 500 responses include a JSON body so CORS middleware can attach headers."""
    if isinstance(exc, StarletteHTTPException):
        raise exc
    logger.exception("Unhandled exception")
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )


class SearchRequest(BaseModel):
    query: str
    filters: dict[str, Any] = Field(default_factory=dict)
    entity_types: list[str] | None = Field(default=None, description="Filter by entity type(s)")
    field_names: list[str] | None = Field(default=None, description="Filter by field name(s)")
    top_k: int = Field(default=20, ge=1, le=50)
    context: str | None = None


class ReferenceResponse(BaseModel):
    title: str
    url: str
    source: str
    type: str
    # Optional richer citation metadata for UI and evaluation (US-010).
    index: int | None = Field(
        default=None,
        description="1-based index matching [n] markers in the summary, when available.",
    )
    typed_id: str | None = Field(
        default=None,
        description="Short, answer-local typed ID such as BUG-8 or FR-3.",
    )
    entity_type: str | None = Field(
        default=None,
        description="Canonical entity type for the cited item (e.g. feature_request, bug).",
    )
    entity_id: str | None = Field(
        default=None,
        description="Canonical entity id in the underlying store, when available.",
    )


class SearchResponse(BaseModel):
    summary: str
    references: list[ReferenceResponse]
    raw_results: list[dict[str, Any]]
    degraded: bool = False


class MondayEntityMappingConfig(BaseModel):
    """Per-entity mapping config for an integration like Monday.com.

    This is intentionally generic so future integrations (e.g. Jira) can adopt the same shape.
    """

    entity_type: str
    board_ids: list[str] = Field(default_factory=list)
    direction: Literal["two_way", "monday_to_os"] = "two_way"
    field_mappings: dict[str, str] = Field(default_factory=dict)


class MondayIntegrationConfigRequest(BaseModel):
    enabled: bool = True
    api_key: str | None = None
    board_ids: list[str] = Field(default_factory=list)
    entity_mappings: dict[str, str] = Field(default_factory=dict)
    # Optional richer, per-entity mapping config (used by US-007 mapping wizard).
    entity_configs: dict[str, MondayEntityMappingConfig] = Field(default_factory=dict)
    sync_interval_seconds: int = Field(default=7200, ge=300, le=86400)
    # Tenant subdomain for item URLs, e.g. "my-team" -> https://my-team.monday.com/boards/...
    subdomain: str | None = None


class MondayIntegrationConfigResponse(BaseModel):
    source: str = "monday"
    enabled: bool
    api_key_set: bool
    board_ids: list[str]
    entity_mappings: dict[str, str]
    # Mirrors request.entity_configs when populated; empty for legacy configs.
    entity_configs: dict[str, MondayEntityMappingConfig] = Field(default_factory=dict)
    sync_interval_seconds: int
    subdomain: str | None = None
    updated_at: str | None = None


class MondayTestConnectionRequest(BaseModel):
    api_key: str | None = None


class MondayTestConnectionResponse(BaseModel):
    ok: bool
    detail: str


class MondayBoardColumn(BaseModel):
    id: str
    title: str
    type: str | None = None


class MondayBoardSchema(BaseModel):
    id: str
    name: str
    columns: list[MondayBoardColumn] = Field(default_factory=list)


class MondaySchemaResponse(BaseModel):
    boards: list[MondayBoardSchema] = Field(default_factory=list)


class MondayColumnRef(BaseModel):
    id: str
    title: str | None = None  # optional; backend uses id as fallback for matching


class MondaySuggestFieldMappingRequest(BaseModel):
    entity_type: str
    source_columns: list[MondayColumnRef] = Field(default_factory=list)


class MondaySuggestFieldMappingResponse(BaseModel):
    field_mappings: dict[str, str] = Field(default_factory=dict)


class MondayPrepareResponse(BaseModel):
    ok: bool
    detail: str
    fetched: int = 0
    embedded: int = 0
    errors: int = 0
    total_entities: int = 0


VECTOR_LIMIT_LOCAL = 20_000
VECTOR_WARN_THRESHOLD = 0.8


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/system/vectors")
async def system_vectors() -> dict:
    """Return vector count, storage mode, and limit status."""
    settings = get_settings()
    mode = settings.qdrant_mode
    limit = VECTOR_LIMIT_LOCAL if mode == "local" else None

    count = 0
    if _vector_store:
        try:
            count = await _vector_store.count()
        except Exception:
            pass

    result: dict = {"count": count, "mode": mode}
    if limit is not None:
        result["limit"] = limit
        result["usage_pct"] = round(count / limit * 100, 1) if limit > 0 else 0
        result["warning"] = count >= int(limit * VECTOR_WARN_THRESHOLD)
        result["blocked"] = count >= limit
    return result


@app.get("/sources")
async def list_sources() -> dict[str, list[str]]:
    from research_agent.storage.models import EntityType

    return {
        "sources": [s.value for s in SourceSystem],
        "entity_types": [t.value for t in EntityType],
    }


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled error: %s", str(exc))
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "error_type": type(exc).__name__},
    )


@app.post("/search_memories", response_model=SearchResponse)
async def search_memories(request: SearchRequest) -> SearchResponse:
    if _memory_service is None:
        raise HTTPException(status_code=503, detail="Service not initialized")

    if not request.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty")

    start = time.time()
    filters = request.filters

    # When any integration is enabled, restrict search to those sources only (exclude mock)
    allowed_sources: list[str] | None = None
    if _db:
        enabled: list[str] = []
        for name in ("monday", "notion", "jira"):
            cfg = await _db.get_integration_config(name)
            if cfg and cfg.get("enabled"):
                enabled.append(name)
        if enabled:
            allowed_sources = enabled

    try:
        result = await _memory_service.search_memories(
            query=request.query,
            top_k=request.top_k,
            entity_types=request.entity_types or filters.get("entity_types"),
            field_names=request.field_names or filters.get("field_names"),
            source=filters.get("source"),
            allowed_sources=allowed_sources,
            date_from=filters.get("date_from"),
            date_to=filters.get("date_to"),
            tags=filters.get("tags"),
            context=request.context,
        )
    except Exception as err:
        logger.exception("Search failed for query: %s", request.query[:100])
        raise HTTPException(
            status_code=502,
            detail="Search service temporarily unavailable. Please try again.",
        ) from err

    duration_ms = int((time.time() - start) * 1000)
    logger.info(
        "Search completed",
        extra={
            "query": request.query[:100],
            "count": len(result.raw_results),
            "duration_ms": duration_ms,
        },
    )

    return SearchResponse(
        summary=result.summary,
        references=[
            ReferenceResponse(**ref) for ref in result.references
        ],
        raw_results=result.raw_results,
        degraded=result.degraded,
    )


@app.get("/integrations/monday", response_model=MondayIntegrationConfigResponse)
async def get_monday_integration_config() -> MondayIntegrationConfigResponse:
    if _db is None:
        raise HTTPException(status_code=503, detail="Service not initialized")

    config = await _db.get_integration_config("monday")
    if config is None:
        return MondayIntegrationConfigResponse(
            enabled=False,
            api_key_set=False,
            board_ids=[],
            entity_mappings={},
            entity_configs={},
            sync_interval_seconds=7200,
            subdomain=None,
            updated_at=None,
        )

    return MondayIntegrationConfigResponse(
        enabled=bool(config["enabled"]),
        api_key_set=bool(config.get("api_key")),
        board_ids=list(config.get("board_ids", [])),
        entity_mappings=dict(config.get("entity_mappings", {})),
        entity_configs={
            key: MondayEntityMappingConfig(**value)
            for key, value in dict(config.get("entity_configs", {})).items()
        },
        sync_interval_seconds=int(config.get("sync_interval_seconds", 7200)),
        subdomain=config.get("subdomain"),
        updated_at=config["updated_at"].isoformat() if config.get("updated_at") else None,
    )


@app.put("/integrations/monday", response_model=MondayIntegrationConfigResponse)
async def upsert_monday_integration_config(
    request: MondayIntegrationConfigRequest,
) -> MondayIntegrationConfigResponse:
    if _db is None:
        raise HTTPException(status_code=503, detail="Service not initialized")

    existing = await _db.get_integration_config("monday")
    api_key = request.api_key
    if api_key is None and existing is not None:
        api_key = str(existing.get("api_key", ""))

    subdomain = request.subdomain
    if api_key:
        slug = await _fetch_monday_account_slug(api_key)
        if slug:
            subdomain = slug
        elif subdomain is None and existing:
            subdomain = existing.get("subdomain")

    config = await _db.upsert_integration_config(
        source="monday",
        enabled=request.enabled,
        api_key=api_key,
        board_ids=request.board_ids,
        entity_mappings=request.entity_mappings,
        entity_configs={
            key: value.model_dump()
            for key, value in request.entity_configs.items()
        },
        sync_interval_seconds=request.sync_interval_seconds,
        subdomain=subdomain,
    )

    return MondayIntegrationConfigResponse(
        enabled=bool(config["enabled"]),
        api_key_set=bool(config.get("api_key")),
        board_ids=list(config.get("board_ids", [])),
        entity_mappings=dict(config.get("entity_mappings", {})),
        entity_configs={
            key: MondayEntityMappingConfig(**value)
            for key, value in dict(config.get("entity_configs", {})).items()
        },
        sync_interval_seconds=int(config.get("sync_interval_seconds", 7200)),
        subdomain=config.get("subdomain"),
        updated_at=config["updated_at"].isoformat() if config.get("updated_at") else None,
    )


@app.post("/integrations/monday/test", response_model=MondayTestConnectionResponse)
async def test_monday_connection(
    request: MondayTestConnectionRequest,
) -> MondayTestConnectionResponse:
    if _db is None:
        raise HTTPException(status_code=503, detail="Service not initialized")

    config = await _db.get_integration_config("monday")
    api_key = request.api_key or (str(config.get("api_key")) if config else "")
    if not api_key:
        raise HTTPException(status_code=400, detail="Monday API key is required")

    connector = MondayConnector(
        api_key=api_key,
        board_id="0",
        entity_type="feature_request",
        field_mappings={"name": "title"},
    )
    try:
        ok = await connector.health_check()
    finally:
        await connector.close()

    if not ok:
        raise HTTPException(
            status_code=502,
            detail="Failed to connect to Monday API. Check API key and permissions.",
        )

    return MondayTestConnectionResponse(ok=True, detail="Monday connection successful")


@app.post("/integrations/monday/prepare", response_model=MondayPrepareResponse)
async def prepare_monday_search() -> MondayPrepareResponse:
    """
    Run a Monday-only sync so newly configured mappings are ingested and indexed for search.

    This is used by the UI after the mapping wizard completes, to confirm search readiness.
    """
    if _db is None:
        raise HTTPException(status_code=503, detail="Service not initialized")

    settings = get_settings()

    if settings.qdrant_mode == "local" and _vector_store:
        try:
            current_count = await _vector_store.count()
            if current_count >= VECTOR_LIMIT_LOCAL:
                raise HTTPException(
                    status_code=429,
                    detail=(
                        f"Vector limit reached ({current_count:,}/{VECTOR_LIMIT_LOCAL:,}). "
                        "Upgrade to Docker or Qdrant Cloud mode to continue adding data."
                    ),
                )
        except HTTPException:
            raise
        except Exception:
            pass

    if not settings.openai_api_key:
        raise HTTPException(
            status_code=400,
            detail="OpenAI API key is required to embed Monday data for search.",
        )

    # Build connectors from current integration config and keep only Monday.
    try:
        connectors = await _build_connectors(_db)
    except Exception as e:
        logger.exception("Failed to build connectors for prepare")
        raise HTTPException(status_code=500, detail="Failed to load Monday integration config.") from e

    monday_connectors = [c for c in connectors if getattr(c, "source_name", "") == "monday"]
    if not monday_connectors:
        raise HTTPException(
            status_code=400,
            detail="Monday integration is not configured or enabled. Save mappings first.",
        )

    # Use app's vector store when available to avoid double-opening local Qdrant (SQLite locking).
    vector_store: QdrantStore
    own_store = False
    if _vector_store is not None:
        vector_store = _vector_store
    else:
        vector_store = create_vector_store(settings)
        own_store = True

    embedder = OpenAIEmbeddingProvider(
        api_key=settings.openai_api_key,
        model=settings.embedding_model,
    )

    try:
        await vector_store.ensure_collection(embedder.dimension())
        engine = SyncEngine(
            db=_db,
            vector_store=vector_store,
            embedding_provider=embedder,
            connectors=monday_connectors,
        )
        result = await engine.sync_all()
    except Exception as e:
        logger.exception("Monday prepare sync failed")
        raise HTTPException(
            status_code=500,
            detail="Sync failed. Check server logs for details.",
        ) from e
    finally:
        if own_store:
            await vector_store.close()

    stats = result.get("connectors", {}).get("monday", {}) if isinstance(result, dict) else {}
    fetched = int(stats.get("fetched", 0) or 0)
    embedded = int(stats.get("embedded", 0) or 0)
    errors = int(stats.get("errors", 0) or 0)

    # Count total Monday entities in the canonical DB for UX feedback.
    total_entities = 0
    try:
        async with _db.session() as session:
            from sqlalchemy import select, func  # local import to avoid global dependency churn

            result_count = await session.execute(
                select(func.count()).select_from(EntityRow).where(EntityRow.source_system == SourceSystem.MONDAY.value)
            )
            total_entities = int(result_count.scalar_one() or 0)
    except Exception as e:
        logger.warning("Failed to count Monday entities for prepare response: %s", e)

    ok = not bool(stats.get("error")) and errors == 0
    detail = (
        "Monday data synced and indexed for search."
        if ok
        else "Monday sync completed with errors. Check server logs for details."
    )

    return MondayPrepareResponse(
        ok=ok,
        detail=detail,
        fetched=fetched,
        embedded=embedded,
        errors=errors,
        total_entities=total_entities,
    )


async def _fetch_monday_account_slug(api_key: str) -> str | None:
    """Fetch the account slug from Monday API (for tenant URLs: https://{slug}.monday.com)."""
    query = """
    query {
      me {
        account {
          slug
        }
      }
    }
    """
    headers = {
        "Authorization": api_key,
        "Content-Type": "application/json",
        "API-Version": "2024-10",
    }
    try:
        async with httpx.AsyncClient(headers=headers, timeout=15.0) as client:
            response = await client.post(MONDAY_API_URL, json={"query": query})
            response.raise_for_status()
            data = response.json()
    except Exception:
        logger.warning("Failed to fetch Monday account slug", exc_info=True)
        return None
    slug = (data.get("data") or {}).get("me") or {}
    slug = (slug.get("account") or {}).get("slug")
    return str(slug).strip() if slug else None


async def _fetch_monday_boards_schema(api_key: str) -> list[MondayBoardSchema]:
    """Fetch Monday boards and their columns for mapping UX."""
    query = """
    query {
      boards(limit: 50) {
        id
        name
        columns {
          id
          title
          type
        }
      }
    }
    """
    headers = {
        "Authorization": api_key,
        "Content-Type": "application/json",
        "API-Version": "2024-10",
    }
    async with httpx.AsyncClient(headers=headers, timeout=30.0) as client:
        try:
            response = await client.post(MONDAY_API_URL, json={"query": query})
            response.raise_for_status()
        except httpx.HTTPError as exc:  # pragma: no cover - mapped to HTTPException
            raise HTTPException(
                status_code=502,
                detail=f"Failed to fetch Monday schema: {exc}",
            ) from exc

    payload = response.json()
    boards_raw = payload.get("data", {}).get("boards", []) or []
    boards: list[MondayBoardSchema] = []
    for board in boards_raw:
        columns = [
            MondayBoardColumn(
                id=str(col.get("id", "")),
                title=str(col.get("title", "")),
                type=col.get("type"),
            )
            for col in board.get("columns", []) or []
        ]
        boards.append(
            MondayBoardSchema(
                id=str(board.get("id", "")),
                name=str(board.get("name", "")),
                columns=columns,
            )
        )
    return boards


@app.get("/integrations/monday/schema", response_model=MondaySchemaResponse)
async def get_monday_schema() -> MondaySchemaResponse:
    """Return Monday boards + columns using the stored integration config."""
    if _db is None:
        raise HTTPException(status_code=503, detail="Service not initialized")
    config = await _db.get_integration_config("monday")
    api_key = str(config.get("api_key")) if config else ""
    if not api_key:
        raise HTTPException(status_code=400, detail="Monday API key is required")
    boards = await _fetch_monday_boards_schema(api_key)
    return MondaySchemaResponse(boards=boards)


def _normalize_for_matching(s: str) -> str:
    """Normalize for exact/similar name matching: lower, strip, spaces/dashes -> underscores."""
    if not s or not isinstance(s, str):
        return ""
    return s.lower().strip().replace(" ", "_").replace("-", "_")


def _deterministic_field_mapping(
    source_columns: list[dict],
    canonical_fields: list[str],
) -> dict[str, str]:
    """Match Monday columns to canonical fields by normalized name (column-first, then canonical-first fallback)."""
    result: dict[str, str] = {}
    used_canonical: set[str] = set()
    used_col_ids: set[str] = set()
    canon_set = set(canonical_fields)
    norm_to_canon: dict[str, str] = {_normalize_for_matching(c): c for c in canonical_fields}
    norm_to_canon = {k: v for k, v in norm_to_canon.items() if k}

    def col_title(c: dict) -> str:
        raw = (c.get("title") or "") if c else ""
        return (raw.strip() or (c.get("id") or "")) if c else ""

    # Special: Monday "name" column -> title (exact id match)
    if "title" in canon_set:
        for c in source_columns:
            if c.get("id") == "name":
                result["name"] = "title"
                used_canonical.add("title")
                used_col_ids.add("name")
                break

    # Column-first: for each column, if its title or id normalizes to a canonical, assign it
    for c in source_columns:
        cid = c.get("id") or ""
        if cid in result:
            continue
        title = col_title(c)
        nt = _normalize_for_matching(title)
        ni = _normalize_for_matching(cid)
        for norm in (nt, ni):
            if not norm:
                continue
            canon = norm_to_canon.get(norm)
            if canon and canon not in used_canonical:
                result[cid] = canon
                used_canonical.add(canon)
                used_col_ids.add(cid)
                break

    # Canonical-first fallback: for any canonical still unmapped, find a column by normalized title/id
    for canon in canonical_fields:
        if canon in used_canonical:
            continue
        norm = _normalize_for_matching(canon)
        if not norm:
            continue
        for c in source_columns:
            cid = c.get("id") or ""
            if cid in used_col_ids:
                continue
            if _normalize_for_matching(col_title(c)) == norm or _normalize_for_matching(cid) == norm:
                result[cid] = canon
                used_canonical.add(canon)
                used_col_ids.add(cid)
                break
    return result


def _suggest_field_mapping_via_llm(
    entity_type: str,
    source_columns: list[dict],
    canonical_fields: list[str],
    openai_api_key: str,
) -> dict[str, str]:
    """Use OpenAI to suggest Monday column id -> canonical field name by semantic meaning.
    Uses Product OS field descriptions so the LLM can match e.g. Account->customer, resolution->verdict.
    """
    import json
    import re

    try:
        import openai
    except ImportError:
        return {}

    if not source_columns or not canonical_fields:
        return {}

    columns_desc = ", ".join(f'"{c["id"]}" (label: {c.get("title", c["id"])})' for c in source_columns)
    # Build canonical list with descriptions for semantic matching
    canon_with_desc = []
    for name in canonical_fields:
        desc = CANONICAL_FIELD_DESCRIPTIONS.get(name, name)
        canon_with_desc.append(f'  - "{name}": {desc}')
    canon_block = "\n".join(canon_with_desc)

    prompt = f"""Map Monday.com board columns to Product OS canonical fields by meaning. Entity type: "{entity_type}".

Monday columns (use the column id as the key in your JSON): {columns_desc}

Product OS canonical fields and their meaning (use exactly the field name as the value):
{canon_block}

Match by semantics, not just keywords. Examples:
- Monday "Account" or "Company" -> canonical "customer"
- Monday "Details", "Info", "Notes", "Body" -> canonical "description"
- Monday "Name", "Subject", "Summary" -> canonical "title"
- Monday "Resolution", "Verdict", "Outcome", "Result" -> canonical "resolution"
- Monday "Status", "State", "Stage" -> canonical "status"

Return a JSON object: keys = Monday column ids, values = canonical field names (exactly as listed above). Include every column that clearly matches a canonical field by meaning. Return only valid JSON, no markdown."""

    try:
        client = openai.OpenAI(api_key=openai_api_key)
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
        )
        text = (resp.choices[0].message.content or "").strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)
        out = json.loads(text)
        if not isinstance(out, dict):
            return {}
        valid_ids = {c["id"] for c in source_columns}
        valid_canon = set(canonical_fields)
        return {k: v for k, v in out.items() if k in valid_ids and v in valid_canon}
    except Exception as e:
        logger.warning("LLM field mapping suggestion failed: %s", e)
        return {}


@app.post("/integrations/monday/suggest-field-mapping", response_model=MondaySuggestFieldMappingResponse)
async def suggest_monday_field_mapping(request: MondaySuggestFieldMappingRequest) -> MondaySuggestFieldMappingResponse:
    """Suggest Monday column -> canonical field mapping using LLM (similarity / semantics)."""
    settings = get_settings()
    if not settings.openai_api_key:
        raise HTTPException(status_code=400, detail="OpenAI API key is required for AI suggestions.")

    try:
        et = EntityType(request.entity_type)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Unknown entity_type: {request.entity_type}")

    canonical = list(CANONICAL_FIELDS.get(et, []))
    if not canonical:
        return MondaySuggestFieldMappingResponse(field_mappings={})

    source_columns = [{"id": c.id, "title": (c.title or c.id)} for c in request.source_columns]
    # 1) Deterministic: exact / normalized name match (title, description, status, etc.)
    suggested = _deterministic_field_mapping(source_columns, canonical)
    # 2) LLM for remaining fuzzy matches (don't overwrite deterministic)
    if settings.openai_api_key:
        llm_map = _suggest_field_mapping_via_llm(
            request.entity_type,
            source_columns,
            canonical,
            settings.openai_api_key,
        )
        for col_id, canon in llm_map.items():
            if col_id not in suggested:
                suggested[col_id] = canon
    return MondaySuggestFieldMappingResponse(field_mappings=suggested)


# ---------------------------------------------------------------------------
# Jira integration endpoints (mirrors Monday flow)
# ---------------------------------------------------------------------------

class JiraEntityMappingConfig(BaseModel):
    """Per-entity mapping config for Jira, mirroring MondayEntityMappingConfig."""

    entity_type: str
    project_key: str = ""
    issue_type_names: list[str] = Field(default_factory=list)
    board_id: int | None = None
    sprint_id: int | None = None
    backlog_only: bool = False
    direction: Literal["two_way", "jira_to_os"] = "jira_to_os"
    field_mappings: dict[str, str] = Field(default_factory=dict)


class JiraIntegrationConfigRequest(BaseModel):
    enabled: bool = True
    access_token: str | None = None
    cloud_id: str | None = None
    site_url: str | None = None
    client_id: str | None = None
    client_secret: str | None = None
    entity_configs: dict[str, JiraEntityMappingConfig] = Field(default_factory=dict)
    sync_interval_seconds: int = Field(default=7200, ge=300, le=86400)


class JiraIntegrationConfigResponse(BaseModel):
    source: str = "jira"
    enabled: bool
    access_token_set: bool
    cloud_id: str | None = None
    site_url: str | None = None
    client_id: str | None = None
    client_secret_set: bool = False
    entity_configs: dict[str, JiraEntityMappingConfig] = Field(default_factory=dict)
    sync_interval_seconds: int
    updated_at: str | None = None


class JiraTestConnectionRequest(BaseModel):
    access_token: str | None = None
    cloud_id: str | None = None


class JiraTestConnectionResponse(BaseModel):
    ok: bool
    detail: str


class JiraFieldInfo(BaseModel):
    id: str
    name: str
    custom: bool = False
    schema_type: str | None = None


class JiraIssueTypeInfo(BaseModel):
    id: str | None = None
    name: str


class JiraProjectInfo(BaseModel):
    id: str
    key: str
    name: str


class JiraBoardInfo(BaseModel):
    id: int
    name: str
    type: str | None = None


class JiraSchemaResponse(BaseModel):
    projects: list[JiraProjectInfo] = Field(default_factory=list)
    boards: list[JiraBoardInfo] = Field(default_factory=list)
    issue_types: list[JiraIssueTypeInfo] = Field(default_factory=list)
    fields: list[JiraFieldInfo] = Field(default_factory=list)


class JiraSuggestFieldMappingRequest(BaseModel):
    entity_type: str
    source_fields: list[JiraFieldInfo] = Field(default_factory=list)


class JiraSuggestFieldMappingResponse(BaseModel):
    field_mappings: dict[str, str] = Field(default_factory=dict)


class JiraPrepareResponse(BaseModel):
    ok: bool
    detail: str
    fetched: int = 0
    embedded: int = 0
    errors: int = 0
    total_entities: int = 0


def _get_jira_connector_for_admin(access_token: str, cloud_id: str) -> JiraConnector:
    """Create a temporary JiraConnector for admin/schema operations (not sync)."""
    return JiraConnector(
        access_token=access_token,
        cloud_id=cloud_id,
        project_key="",
        issue_type_names=[],
        entity_type="feature_request",
        field_mappings={"summary": "title"},
    )


async def _resolve_jira_credentials(
    request_token: str | None, request_cloud_id: str | None
) -> tuple[str, str]:
    """Resolve access_token and cloud_id from request or stored config."""
    config = await _db.get_integration_config("jira") if _db else None  # type: ignore[union-attr]
    access_token = request_token or (str(config.get("api_key", "")) if config else "")
    cloud_id = request_cloud_id
    if not cloud_id and config:
        cloud_id = config.get("subdomain") or ""
    if not access_token:
        raise HTTPException(status_code=400, detail="Jira access token is required")
    if not cloud_id:
        raise HTTPException(status_code=400, detail="Jira cloud ID is required")
    return access_token, cloud_id


def _jira_probe_search_url(cloud_id: str, project_key: str | None) -> str:
    """Build search probe URL; if project_key given, probe that project (410 can be project-specific)."""
    from urllib.parse import quote
    if project_key:
        jql = quote(f"project = {project_key} ORDER BY created DESC")
    else:
        jql = quote("order by created DESC")
    return f"https://api.atlassian.com/ex/jira/{cloud_id}/rest/api/3/search/jql?jql={jql}&maxResults=1&fields=key"


async def _jira_find_working_cloud_id(access_token: str, project_key: str | None = None) -> str | None:
    """Probe accessible-resources and return the first cloud_id for which the search API returns 200 (not 410)."""
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resources_resp = await client.get(
                "https://api.atlassian.com/oauth/token/accessible-resources",
                headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"},
            )
            if resources_resp.status_code != 200:
                return None
            resources = resources_resp.json()
            if not resources or not isinstance(resources, list):
                return None
            for r in resources:
                rid = (r.get("id") or "").strip()
                if not rid:
                    continue
                probe_url = _jira_probe_search_url(rid, project_key)
                probe = await client.get(
                    probe_url,
                    headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"},
                )
                if probe.status_code == 200:
                    logger.info(
                        "Jira 410 repair: using cloud_id %s (url=%s)",
                        rid,
                        r.get("url", ""),
                    )
                    return rid
    except Exception as e:
        logger.warning("Jira find working cloud_id failed: %s", e)
    return None


# Scopes needed for Jira REST + Agile (read-only)
JIRA_OAUTH_SCOPES = "read:jira-work read:jira-user read:me offline_access"


async def _get_jira_oauth_client_credentials() -> tuple[str, str]:
    """Return (client_id, client_secret). DB first (from wizard), then env fallback. Env is for debugging only."""
    creds, _ = await _get_jira_oauth_client_credentials_with_source()
    return creds


async def _get_jira_oauth_client_credentials_with_source() -> tuple[tuple[str, str], str]:
    """Return ((client_id, client_secret), source). source is 'db' or 'env'."""
    config = None
    if _db:
        try:
            config = await _db.get_integration_config("jira")  # type: ignore[union-attr]
        except Exception:
            pass
    client_id = (config.get("oauth_client_id") or "").strip() if config else ""
    client_secret = (config.get("oauth_client_secret") or "").strip() if config else ""
    source = "db" if (client_id and client_secret) else "env"
    if not client_id or not client_secret:
        settings = get_settings()
        client_id = client_id or (settings.jira_oauth_client_id or "").strip()
        client_secret = client_secret or (settings.jira_oauth_client_secret or "").strip()
    if not client_id or not client_secret:
        raise HTTPException(
            status_code=400,
            detail="Enter your Jira app Client ID and Client Secret in the Connect Jira step (from Atlassian Developer Console → your app → Settings), then click Connect with Jira (OAuth).",
        )
    return (client_id, client_secret), source


@app.get("/integrations/jira/oauth/ready")
async def jira_oauth_ready() -> dict:
    """
    Return whether OAuth can be started (credentials available from env or DB).
    Used by the wizard to show "Connect with Jira" without requiring form fields.
    """
    try:
        await _get_jira_oauth_client_credentials_with_source()
        return {"ready": True}
    except HTTPException as e:
        return {"ready": False, "message": (e.detail or "Jira OAuth is not configured.")}


@app.get("/integrations/jira/oauth/authorize")
async def jira_oauth_authorize(return_to: str | None = None) -> RedirectResponse:
    """
    Start OAuth 2.0 (3LO) flow: redirect user to Atlassian consent page.
    Uses Client ID and Secret from the integration config (UI) or from env.
    return_to: optional 'integrations' or 'onboarding'; encoded in state and passed back to frontend so redirect lands on the right view.
    """
    (client_id, client_secret), _ = await _get_jira_oauth_client_credentials_with_source()
    settings = get_settings()
    from urllib.parse import urlencode

    state = "jira_os_research"
    if return_to and return_to.strip() in ("integrations", "onboarding"):
        state = f"jira_os_research:{return_to.strip()}"

    params = {
        "audience": "api.atlassian.com",
        "client_id": client_id,
        "scope": JIRA_OAUTH_SCOPES,
        "redirect_uri": settings.jira_oauth_redirect_uri,
        "state": state,
        "response_type": "code",
        "prompt": "consent",
    }
    url = "https://auth.atlassian.com/authorize?" + urlencode(params)
    return RedirectResponse(url=url, status_code=302)


class DebugTokenRequest(BaseModel):
    code: str


@app.post("/integrations/jira/oauth/debug-token")
async def jira_oauth_debug_token(req: DebugTokenRequest) -> dict:
    """
    Test token exchange with a real code from the callback URL.
    POST {"code": "eyJ..."} - paste the code from ?code=XXX in the callback URL.
    Returns the raw Atlassian response (no redirect).
    """
    settings = get_settings()
    try:
        client_id, client_secret = await _get_jira_oauth_client_credentials()
    except HTTPException as e:
        return {"error": e.detail}
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://auth.atlassian.com/oauth/token",
            json={
                "grant_type": "authorization_code",
                "client_id": client_id,
                "client_secret": client_secret,
                "code": req.code.strip(),
                "redirect_uri": settings.jira_oauth_redirect_uri,
            },
            headers={"Content-Type": "application/json"},
        )
    try:
        body = resp.json()
    except Exception:
        body = {"_raw": resp.text[:500]}
    return {"status": resp.status_code, "body": body, "redirect_uri_used": settings.jira_oauth_redirect_uri}


@app.get("/integrations/jira/oauth/debug")
async def jira_oauth_debug():
    """
    Debug OAuth: run a fake token exchange and return credentials state + Atlassian response.
    Use to verify JIRA_OAUTH_* (or JIRA_CLIENT_ID / JIRA_SECRET) and redirect_uri.
    """
    settings = get_settings()
    try:
        client_id, client_secret = await _get_jira_oauth_client_credentials()
    except HTTPException as e:
        return {
            "credentials_loaded": False,
            "error": e.detail,
            "redirect_uri": settings.jira_oauth_redirect_uri,
            "env_client_id_set": bool((settings.jira_oauth_client_id or "").strip()),
            "env_client_secret_set": bool((settings.jira_oauth_client_secret or "").strip()),
        }
    credentials_source = "env" if (settings.jira_oauth_client_id or "").strip() else "db"
    async with httpx.AsyncClient() as client:
        token_resp = await client.post(
            "https://auth.atlassian.com/oauth/token",
            json={
                "grant_type": "authorization_code",
                "client_id": client_id,
                "client_secret": client_secret,
                "code": "debug_fake_code_do_not_use",
                "redirect_uri": settings.jira_oauth_redirect_uri,
            },
            headers={"Content-Type": "application/json"},
        )
        try:
            atlassian_body = token_resp.json()
        except Exception:
            atlassian_body = {"_raw": token_resp.text}
    return {
        "credentials_loaded": True,
        "credentials_source": credentials_source,
        "client_id_prefix": (client_id or "")[:8] + "..." if client_id else "",
        "redirect_uri": settings.jira_oauth_redirect_uri,
        "atlassian_status": token_resp.status_code,
        "atlassian_body": atlassian_body,
        "hint": "401/access_denied = wrong Client ID/Secret or redirect_uri mismatch with Atlassian app Callback URL. 400/invalid_grant = credentials OK, code invalid (expected for this debug call).",
    }


@app.get("/integrations/jira/oauth/callback")
async def jira_oauth_callback(code: str | None = None, state: str | None = None) -> RedirectResponse:
    """
    OAuth callback: exchange authorization code for access token, then redirect to UI
    with token and cloud_id in the URL fragment (so they are not sent to server logs).
    """
    settings = get_settings()
    code = (code or "").strip() if code else None
    if not code:
        error_url = (
            settings.jira_oauth_frontend_origin
            + "/#jira_oauth_error=missing_code"
        )
        return RedirectResponse(url=error_url, status_code=302)
    try:
        (client_id, client_secret), _ = await _get_jira_oauth_client_credentials_with_source()
    except HTTPException:
        error_url = (
            settings.jira_oauth_frontend_origin
            + "/#jira_oauth_error=oauth_not_configured"
        )
        return RedirectResponse(url=error_url, status_code=302)

    # Use same credentials as authorize flow; env_debug_override caused "mismatched aud"
    # when authorize used DB creds but callback used env.

    token_payload = {
        "grant_type": "authorization_code",
        "client_id": client_id,
        "client_secret": client_secret,
        "code": code,
        "redirect_uri": settings.jira_oauth_redirect_uri,
    }
    async with httpx.AsyncClient() as client:
        token_resp = await client.post(
            "https://auth.atlassian.com/oauth/token",
            json=token_payload,
            headers={"Content-Type": "application/json"},
        )
        if token_resp.status_code != 200:
            logger.warning("Jira OAuth token exchange failed: %s", token_resp.text)
            try:
                err_body = token_resp.json()
                err_desc = err_body.get("error_description") or err_body.get("error") or token_resp.text
            except Exception:
                err_desc = token_resp.text or "token_exchange_failed"
            from urllib.parse import quote

            error_fragment = "jira_oauth_error=token_exchange_failed&message=" + quote(
                (err_desc or "Unknown error")[:200]
            )
            error_url = (
                settings.jira_oauth_frontend_origin + "/#" + error_fragment
            )
            return RedirectResponse(url=error_url, status_code=302)

        data = token_resp.json()
        access_token = data.get("access_token")
        if not access_token:
            error_url = (
                settings.jira_oauth_frontend_origin
                + "/#jira_oauth_error=no_access_token"
            )
            return RedirectResponse(url=error_url, status_code=302)

        # Resolve cloud_id and site_url: pick a resource for which the search API returns 200 (not 410).
        # serverInfo can return 200 while search returns 410; probe search so sync works.
        cloud_id = ""
        site_url = ""
        try:
            resources_resp = await client.get(
                "https://api.atlassian.com/oauth/token/accessible-resources",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            if resources_resp.status_code == 200:
                resources = resources_resp.json()
                if resources and isinstance(resources, list):
                    for r in resources:
                        rid = (r.get("id") or "").strip()
                        if not rid:
                            continue
                        probe = await client.get(
                            _jira_probe_search_url(rid, None),
                            headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"},
                        )
                        if probe.status_code == 200:
                            cloud_id = rid
                            site_url = (r.get("url") or "").strip()
                            logger.info(
                                "Jira OAuth: using cloud_id %s (url=%s)",
                                rid,
                                site_url or r.get("url", ""),
                            )
                            break
                    if not cloud_id and resources:
                        first = resources[0]
                        cloud_id = first.get("id", "") or ""
                        site_url = (first.get("url") or "").strip()
        except Exception as e:
            logger.warning("Failed to fetch Jira accessible resources: %s", e)

    # Redirect to frontend with token, cloud_id, and site_url in fragment (client-only, not logged)
    from urllib.parse import urlencode

    fragment_params: dict[str, str] = {"access_token": access_token, "cloud_id": cloud_id}
    if site_url:
        fragment_params["site_url"] = site_url
    if state and ":" in state:
        _return_to = state.split(":", 1)[1].strip()
        if _return_to in ("integrations", "onboarding"):
            fragment_params["return_to"] = _return_to
    fragment = "jira_oauth_connected&" + urlencode(fragment_params)
    redirect_url = settings.jira_oauth_frontend_origin + "/#" + fragment
    return RedirectResponse(url=redirect_url, status_code=302)


@app.get("/integrations/jira", response_model=JiraIntegrationConfigResponse)
async def get_jira_integration_config() -> JiraIntegrationConfigResponse:
    if _db is None:
        raise HTTPException(status_code=503, detail="Service not initialized")

    config = await _db.get_integration_config("jira")
    if config is None:
        return JiraIntegrationConfigResponse(
            enabled=False,
            access_token_set=False,
            cloud_id=None,
            site_url=None,
            client_id=None,
            client_secret_set=False,
            entity_configs={},
            sync_interval_seconds=7200,
            updated_at=None,
        )

    return JiraIntegrationConfigResponse(
        enabled=bool(config["enabled"]),
        access_token_set=bool(config.get("api_key")),
        cloud_id=config.get("subdomain"),
        site_url=config.get("site_url"),
        client_id=config.get("oauth_client_id"),
        client_secret_set=bool(config.get("oauth_client_secret")),
        entity_configs={
            key: JiraEntityMappingConfig(**value)
            for key, value in dict(config.get("entity_configs", {})).items()
        },
        sync_interval_seconds=int(config.get("sync_interval_seconds", 7200)),
        updated_at=config["updated_at"].isoformat() if config.get("updated_at") else None,
    )


@app.put("/integrations/jira", response_model=JiraIntegrationConfigResponse)
async def upsert_jira_integration_config(
    request: JiraIntegrationConfigRequest,
) -> JiraIntegrationConfigResponse:
    if _db is None:
        raise HTTPException(status_code=503, detail="Service not initialized")

    existing = await _db.get_integration_config("jira")
    access_token = request.access_token
    if access_token is None and existing is not None:
        access_token = str(existing.get("api_key", ""))
    cloud_id = request.cloud_id
    if cloud_id is None and existing is not None:
        cloud_id = existing.get("subdomain")
    site_url = request.site_url
    if site_url is None and existing is not None:
        site_url = existing.get("site_url")
    oauth_client_id = request.client_id
    if oauth_client_id is None and existing is not None:
        oauth_client_id = existing.get("oauth_client_id")
    oauth_client_secret = request.client_secret
    if oauth_client_secret is None and existing is not None:
        oauth_client_secret = existing.get("oauth_client_secret")
    if oauth_client_id is not None and isinstance(oauth_client_id, str):
        oauth_client_id = oauth_client_id.strip()
    if oauth_client_secret is not None and isinstance(oauth_client_secret, str):
        oauth_client_secret = oauth_client_secret.strip()

    config = await _db.upsert_integration_config(
        source="jira",
        enabled=request.enabled,
        api_key=access_token,
        board_ids=[],
        entity_mappings={},
        entity_configs={
            key: value.model_dump()
            for key, value in request.entity_configs.items()
        },
        sync_interval_seconds=request.sync_interval_seconds,
        subdomain=cloud_id,
        site_url=site_url,
        oauth_client_id=oauth_client_id,
        oauth_client_secret=oauth_client_secret,
    )

    return JiraIntegrationConfigResponse(
        enabled=bool(config["enabled"]),
        access_token_set=bool(config.get("api_key")),
        cloud_id=config.get("subdomain"),
        site_url=config.get("site_url"),
        client_id=config.get("oauth_client_id"),
        client_secret_set=bool(config.get("oauth_client_secret")),
        entity_configs={
            key: JiraEntityMappingConfig(**value)
            for key, value in dict(config.get("entity_configs", {})).items()
        },
        sync_interval_seconds=int(config.get("sync_interval_seconds", 7200)),
        updated_at=config["updated_at"].isoformat() if config.get("updated_at") else None,
    )


@app.post("/integrations/jira/test", response_model=JiraTestConnectionResponse)
async def test_jira_connection(
    request: JiraTestConnectionRequest,
) -> JiraTestConnectionResponse:
    if _db is None:
        raise HTTPException(status_code=503, detail="Service not initialized")

    access_token, cloud_id = await _resolve_jira_credentials(
        request.access_token, request.cloud_id
    )

    connector = _get_jira_connector_for_admin(access_token, cloud_id)
    try:
        ok = await connector.health_check()
    finally:
        await connector.close()

    if not ok:
        raise HTTPException(
            status_code=502,
            detail="Failed to connect to Jira. Check OAuth token and cloud ID.",
        )

    return JiraTestConnectionResponse(ok=True, detail="Jira connection successful")


@app.get("/integrations/jira/schema", response_model=JiraSchemaResponse)
async def get_jira_schema(project_key: str | None = None) -> JiraSchemaResponse:
    """Return Jira projects, boards, issue types, and fields for mapping UI."""
    if _db is None:
        raise HTTPException(status_code=503, detail="Service not initialized")

    access_token, cloud_id = await _resolve_jira_credentials(None, None)
    connector = _get_jira_connector_for_admin(access_token, cloud_id)

    try:
        projects_raw = await connector.fetch_projects()
        projects = [
            JiraProjectInfo(
                id=str(p.get("id", "")),
                key=str(p.get("key", "")),
                name=str(p.get("name", "")),
            )
            for p in projects_raw
        ]

        boards: list[JiraBoardInfo] = []
        boards_raw = await connector.fetch_boards(project_key)
        for b in boards_raw:
            boards.append(JiraBoardInfo(
                id=int(b.get("id", 0)),
                name=str(b.get("name", "")),
                type=b.get("type"),
            ))

        issue_types: list[JiraIssueTypeInfo] = []
        if project_key:
            it_raw = await connector.fetch_issue_types(project_key)
            issue_types = [
                JiraIssueTypeInfo(id=str(it.get("id", "")), name=str(it.get("name", "")))
                for it in it_raw
            ]

        fields_raw = await connector.fetch_fields()
        fields = [
            JiraFieldInfo(
                id=str(f.get("id", "")),
                name=str(f.get("name", "")),
                custom=bool(f.get("custom", False)),
                schema_type=(f.get("schema", {}) or {}).get("type"),
            )
            for f in fields_raw
        ]
    finally:
        await connector.close()

    return JiraSchemaResponse(
        projects=projects, boards=boards, issue_types=issue_types, fields=fields
    )


@app.post(
    "/integrations/jira/suggest-field-mapping",
    response_model=JiraSuggestFieldMappingResponse,
)
async def suggest_jira_field_mapping(
    request: JiraSuggestFieldMappingRequest,
) -> JiraSuggestFieldMappingResponse:
    """Suggest Jira field -> canonical field mapping using deterministic + LLM."""
    settings = get_settings()

    try:
        et = EntityType(request.entity_type)
    except ValueError:
        raise HTTPException(
            status_code=400, detail=f"Unknown entity_type: {request.entity_type}"
        )

    canonical = list(CANONICAL_FIELDS.get(et, []))
    if not canonical:
        return JiraSuggestFieldMappingResponse(field_mappings={})

    source_columns = [
        {"id": f.id, "title": f.name or f.id} for f in request.source_fields
    ]

    suggested = _deterministic_field_mapping(source_columns, canonical)

    if settings.openai_api_key:
        llm_map = _suggest_field_mapping_via_llm(
            request.entity_type, source_columns, canonical, settings.openai_api_key
        )
        for col_id, canon in llm_map.items():
            if col_id not in suggested:
                suggested[col_id] = canon

    return JiraSuggestFieldMappingResponse(field_mappings=suggested)


@app.post("/integrations/jira/prepare", response_model=JiraPrepareResponse)
async def prepare_jira_search() -> JiraPrepareResponse:
    """Run a Jira-only sync so newly configured mappings are ingested and indexed."""
    if _db is None:
        raise HTTPException(status_code=503, detail="Service not initialized")

    settings = get_settings()

    if settings.qdrant_mode == "local" and _vector_store:
        try:
            current_count = await _vector_store.count()
            if current_count >= VECTOR_LIMIT_LOCAL:
                raise HTTPException(
                    status_code=429,
                    detail=(
                        f"Vector limit reached ({current_count:,}/{VECTOR_LIMIT_LOCAL:,}). "
                        "Upgrade to Docker or Qdrant Cloud mode to continue adding data."
                    ),
                )
        except HTTPException:
            raise
        except Exception:
            pass

    if not settings.openai_api_key:
        raise HTTPException(
            status_code=400,
            detail="OpenAI API key is required to embed Jira data for search.",
        )

    try:
        connectors = await _build_connectors(_db)
    except Exception as e:
        logger.exception("Failed to build connectors for Jira prepare")
        raise HTTPException(
            status_code=500, detail="Failed to load Jira integration config."
        ) from e

    jira_connectors = [
        c for c in connectors if getattr(c, "source_name", "") == "jira"
    ]
    if not jira_connectors:
        raise HTTPException(
            status_code=400,
            detail="Jira integration is not configured or enabled. Save mappings first.",
        )

    vector_store: QdrantStore
    own_store = False
    if _vector_store is not None:
        vector_store = _vector_store
    else:
        vector_store = create_vector_store(settings)
        own_store = True

    embedder = OpenAIEmbeddingProvider(
        api_key=settings.openai_api_key,
        model=settings.embedding_model,
    )

    try:
        await vector_store.ensure_collection(embedder.dimension())
        engine = SyncEngine(
            db=_db,
            vector_store=vector_store,
            embedding_provider=embedder,
            connectors=jira_connectors,
        )
        result = await engine.sync_all()
    except Exception as e:
        logger.exception("Jira prepare sync failed")
        raise HTTPException(
            status_code=500,
            detail="Sync failed. Check server logs for details.",
        ) from e
    finally:
        if own_store:
            await vector_store.close()

    stats = (
        result.get("connectors", {}).get("jira", {})
        if isinstance(result, dict)
        else {}
    )
    # If we got 410 (stale/deprecated cloud_id), try to repair: find a working cloud and retry once
    if stats.get("error") and "410" in (stats.get("message") or ""):
        jira_config = await _db.get_integration_config("jira")
        if jira_config:
            token = (jira_config.get("api_key") or "").strip()
            current_cloud = (jira_config.get("subdomain") or "").strip()
            if token:
                entity_configs = jira_config.get("entity_configs") or {}
                first_project = next(
                    (str(c.get("project_key", "")).strip() for c in entity_configs.values() if isinstance(c, dict) and c.get("project_key")),
                    None,
                )
                working_cloud = await _jira_find_working_cloud_id(token, first_project)
                if working_cloud and working_cloud != current_cloud:
                    await _db.upsert_integration_config(
                        source="jira",
                        enabled=jira_config.get("enabled", True),
                        api_key=token,
                        board_ids=jira_config.get("board_ids", []),
                        entity_mappings=jira_config.get("entity_mappings", {}),
                        entity_configs=jira_config.get("entity_configs"),
                        sync_interval_seconds=int(jira_config.get("sync_interval_seconds", 7200)),
                        subdomain=working_cloud,
                        oauth_client_id=jira_config.get("oauth_client_id"),
                        oauth_client_secret=jira_config.get("oauth_client_secret"),
                    )
                    try:
                        connectors_retry = await _build_connectors(_db)
                        jira_connectors_retry = [
                            c for c in connectors_retry if getattr(c, "source_name", "") == "jira"
                        ]
                        if jira_connectors_retry:
                            engine_retry = SyncEngine(
                                db=_db,
                                vector_store=vector_store,
                                embedding_provider=embedder,
                                connectors=jira_connectors_retry,
                            )
                            result = await engine_retry.sync_all()
                            stats = (
                                result.get("connectors", {}).get("jira", {})
                                if isinstance(result, dict)
                                else {}
                            )
                    except Exception as retry_e:
                        logger.warning("Jira 410 repair retry failed: %s", retry_e)

    fetched = int(stats.get("fetched", 0) or 0)
    embedded = int(stats.get("embedded", 0) or 0)
    errors = int(stats.get("errors", 0) or 0)

    total_entities = 0
    try:
        async with _db.session() as session:
            from sqlalchemy import func, select as sa_select

            result_count = await session.execute(
                sa_select(func.count())
                .select_from(EntityRow)
                .where(EntityRow.source_system == SourceSystem.JIRA.value)
            )
            total_entities = int(result_count.scalar_one() or 0)
    except Exception as e:
        logger.warning("Failed to count Jira entities for prepare response: %s", e)

    ok = not bool(stats.get("error")) and errors == 0
    detail = (
        "Jira data synced and indexed for search."
        if ok
        else (stats.get("message") or "Jira sync completed with errors. Check server logs for details.")
    )

    return JiraPrepareResponse(
        ok=ok,
        detail=detail,
        fetched=fetched,
        embedded=embedded,
        errors=errors,
        total_entities=total_entities,
    )
