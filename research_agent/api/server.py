"""FastAPI REST API — POST /search_memories, GET /health, GET /sources."""

from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager
from typing import Any, Literal

import httpx
from fastapi import FastAPI, HTTPException, Request
from starlette.exceptions import HTTPException as StarletteHTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from research_agent.config.loader import create_vector_store, get_settings
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
        for name in ("monday", "notion"):
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
