"""FastAPI REST API — POST /search_memories, GET /health, GET /sources."""

from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager
from typing import Any, Literal

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from research_agent.config.loader import get_settings
from research_agent.connectors.monday_connector import MONDAY_API_URL, MondayConnector
from research_agent.embedding.openai_provider import OpenAIEmbeddingProvider
from research_agent.logging_config import configure_logging
from research_agent.memory.memory_service import MemoryService
from research_agent.storage.db import Database
from research_agent.storage.models import SourceSystem, EntityRow
from research_agent.synthesis.summarizer import Summarizer
from research_agent.vector.qdrant_client import QdrantStore
from research_agent.sync.sync_all import SyncEngine
from research_agent.__main__ import _build_connectors

logger = logging.getLogger(__name__)

_memory_service: MemoryService | None = None
_db: Database | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):  # type: ignore[no-untyped-def]
    global _memory_service
    global _db
    settings = get_settings()
    configure_logging(settings.log_level)

    db = Database(db_path=settings.database_path)
    await db.init()
    _db = db

    vector_store = QdrantStore(host=settings.qdrant_host, port=settings.qdrant_port)
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


class MondayPrepareResponse(BaseModel):
    ok: bool
    detail: str
    fetched: int = 0
    embedded: int = 0
    errors: int = 0
    total_entities: int = 0


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


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
    if not settings.openai_api_key:
        raise HTTPException(
            status_code=400,
            detail="OpenAI API key is required to embed Monday data for search.",
        )

    # Build connectors from current integration config and keep only Monday.
    connectors = await _build_connectors(_db)
    monday_connectors = [c for c in connectors if getattr(c, "source_name", "") == "monday"]
    if not monday_connectors:
        raise HTTPException(
            status_code=400,
            detail="Monday integration is not configured or enabled. Save mappings first.",
        )

    vector_store = QdrantStore(host=settings.qdrant_host, port=settings.qdrant_port)
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
    finally:
        await vector_store.close()

    stats = result.get("connectors", {}).get("monday", {}) if isinstance(result, dict) else {}
    fetched = int(stats.get("fetched", 0) or 0)
    embedded = int(stats.get("embedded", 0) or 0)
    errors = int(stats.get("errors", 0) or 0)

    # Count total Monday entities in the canonical DB for UX feedback.
    total_entities = 0
    async with _db.session() as session:
        from sqlalchemy import select, func  # local import to avoid global dependency churn

        result_count = await session.execute(
            select(func.count()).select_from(EntityRow).where(EntityRow.source_system == SourceSystem.MONDAY.value)
        )
        total_entities = int(result_count.scalar_one() or 0)

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
