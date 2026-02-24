"""FastAPI REST API — POST /search_memories, GET /health, GET /sources."""

from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from research_agent.config.loader import get_settings
from research_agent.connectors.monday_connector import MondayConnector
from research_agent.embedding.openai_provider import OpenAIEmbeddingProvider
from research_agent.logging_config import configure_logging
from research_agent.memory.memory_service import MemoryService
from research_agent.storage.db import Database
from research_agent.storage.models import SourceSystem
from research_agent.synthesis.summarizer import Summarizer
from research_agent.vector.qdrant_client import QdrantStore

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
    top_k: int = Field(default=10, ge=1, le=50)
    context: str | None = None


class ReferenceResponse(BaseModel):
    title: str
    url: str
    source: str
    type: str


class SearchResponse(BaseModel):
    summary: str
    references: list[ReferenceResponse]
    raw_results: list[dict[str, Any]]
    degraded: bool = False


class MondayIntegrationConfigRequest(BaseModel):
    enabled: bool = True
    api_key: str | None = None
    board_ids: list[str] = Field(default_factory=list)
    entity_mappings: dict[str, str] = Field(default_factory=dict)
    sync_interval_seconds: int = Field(default=7200, ge=300, le=86400)


class MondayIntegrationConfigResponse(BaseModel):
    source: str = "monday"
    enabled: bool
    api_key_set: bool
    board_ids: list[str]
    entity_mappings: dict[str, str]
    sync_interval_seconds: int
    updated_at: str | None = None


class MondayTestConnectionRequest(BaseModel):
    api_key: str | None = None


class MondayTestConnectionResponse(BaseModel):
    ok: bool
    detail: str


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

    try:
        result = await _memory_service.search_memories(
            query=request.query,
            top_k=request.top_k,
            entity_types=request.entity_types or filters.get("entity_types"),
            field_names=request.field_names or filters.get("field_names"),
            source=filters.get("source"),
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
            sync_interval_seconds=7200,
            updated_at=None,
        )

    return MondayIntegrationConfigResponse(
        enabled=bool(config["enabled"]),
        api_key_set=bool(config.get("api_key")),
        board_ids=list(config.get("board_ids", [])),
        entity_mappings=dict(config.get("entity_mappings", {})),
        sync_interval_seconds=int(config.get("sync_interval_seconds", 7200)),
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

    config = await _db.upsert_integration_config(
        source="monday",
        enabled=request.enabled,
        api_key=api_key,
        board_ids=request.board_ids,
        entity_mappings=request.entity_mappings,
        sync_interval_seconds=request.sync_interval_seconds,
    )

    return MondayIntegrationConfigResponse(
        enabled=bool(config["enabled"]),
        api_key_set=bool(config.get("api_key")),
        board_ids=list(config.get("board_ids", [])),
        entity_mappings=dict(config.get("entity_mappings", {})),
        sync_interval_seconds=int(config.get("sync_interval_seconds", 7200)),
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
