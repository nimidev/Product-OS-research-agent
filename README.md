# Research Agent

AI-powered organizational knowledge search. Syncs data from Monday.com, Notion, and other sources into a vector database, then exposes semantic search via MCP for Cursor and a REST API.

## Prerequisites

- Python 3.11+
- **Docker** (for Qdrant) — start Docker Desktop before `docker-compose up`
- OpenAI API key (for embeddings and synthesis)

## Quick Start

```bash
# 1. Clone and set up
git clone <repo-url>
cd Product-OS-Research-Agent
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 2. Configure
cp .env.example .env
# Edit .env — set OPENAI_API_KEY at minimum

# 3. Start Qdrant (requires Docker Desktop or Docker daemon to be running)
docker-compose up qdrant -d

# 4. Seed with canonical mock data (run once; re-run to re-ingest and replace existing data)
python -m research_agent seed

# 5. Start the API
python -m research_agent serve
# API at http://localhost:8000
# Health check: GET /health
# Search: POST /search_memories

# 6. Or run the MCP server for Cursor
python -m research_agent mcp
```

## Architecture

```
Cursor IDE → MCP (stdio) → Research Agent → Qdrant (vectors) + SQLite (canonical store)
                                ↑
                           Connectors (Monday.com, Notion, ...)
```

### Components

| Component | Path | Purpose |
|-----------|------|---------|
| Storage | `research_agent/storage/` | SQLite canonical data model (Entity, EntityField, Chunk + SyncState) |
| Embedding | `research_agent/embedding/` | EmbeddingProvider interface + OpenAI impl + chunker |
| Vector | `research_agent/vector/` | Qdrant client wrapper with parent-dedup search |
| Memory | `research_agent/memory/` | Core search/add service orchestrating all layers |
| Synthesis | `research_agent/synthesis/` | LLM-powered summary generation with citations |
| API | `research_agent/api/` | FastAPI REST endpoints |
| MCP | `research_agent/mcp/` | MCP server for Cursor integration |
| Connectors | `research_agent/connectors/` | Pluggable data source connectors |
| Sync | `research_agent/sync/` | Cron-style sync engine orchestrating connectors |
| Config | `research_agent/config/` | Settings from .env (Phase 1) or config.yaml (Phase 2+) |

## CLI Commands

```bash
python -m research_agent seed    # Load fixtures → SQLite + Qdrant
python -m research_agent serve   # Start FastAPI server on :8000
python -m research_agent mcp     # Start MCP server (stdio)
python -m research_agent sync    # Run sync with configured connectors
```

## API Endpoints

### `GET /health`
Returns `{"status": "ok"}`.

### `GET /sources`
Returns available data sources and entity types (e.g. `feature_request`, `bug`, `meeting_note`, `prd`, `roadmap_item`, `support_ticket`).

### `POST /search_memories`
```json
{
  "query": "What pain points do users have with onboarding?",
  "entity_types": ["feature_request", "support_ticket"],
  "field_names": ["description", "transcript"],
  "filters": {
    "source": "mock",
    "entity_types": ["feature_request"],
    "date_from": "2025-01-01",
    "date_to": "2025-12-31",
    "tags": ["enterprise"]
  },
  "top_k": 10,
  "context": "Previous conversation context for follow-ups"
}
```

Response:
```json
{
  "summary": "AI-synthesized answer with [1] inline citations...",
  "references": [{"title": "...", "url": "...", "source": "mock", "type": "feature_request"}],
  "raw_results": [{"id": "...", "title": "...", "body": "...", "entity_type": "feature_request", "field_name": "description", ...}],
  "degraded": false
}
```

## MCP Configuration for Cursor

Add to your Cursor MCP settings:

```json
{
  "mcpServers": {
    "research-agent": {
      "command": "python",
      "args": ["-m", "research_agent", "mcp"],
      "cwd": "/path/to/Product-OS-Research-Agent",
      "env": {
        "OPENAI_API_KEY": "sk-..."
      }
    }
  }
}
```

### MCP Tools

- **`search_memories`** — Search the knowledge base with optional filters and conversation context. Returns AI-synthesized summary with source citations.
- **`list_sources`** — List available data sources and entity types.

## Connectors

### Adding a New Connector

1. Subclass `BaseConnector` from `research_agent/connectors/base.py`
2. Implement `list_updated_entities(since)` and `normalize_item(raw) -> Entity`
3. Add mapping in `config/mappings.yaml` (see `config/mappings.example.yaml`)

### Built-in Connectors

- **Monday.com** — GraphQL API with configurable board/column mapping
- **Notion** — Database queries with full page content extraction

## Configuration

### Phase 1 (`.env`)
```bash
OPENAI_API_KEY=sk-...
QDRANT_HOST=localhost
QDRANT_PORT=6333
LLM_MODEL=gpt-4o-mini
EMBEDDING_MODEL=text-embedding-3-small
DATABASE_PATH=research_agent.db
LOG_LEVEL=INFO
```

### Connector mappings (`config/mappings.yaml`)
Copy `config/mappings.example.yaml` to `config/mappings.yaml` and set your Monday board IDs and Notion database IDs. Field mappings define how source columns map to canonical entity fields (e.g. `name` → `title`, `text0` → `description`). Used by `python -m research_agent sync`.

## Development

```bash
# Install deps
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Run tests
python -m pytest tests/ -v

# Lint
ruff check research_agent/ tests/
ruff format research_agent/ tests/

# Search quality evaluation (requires seeded Qdrant)
python -m tests.evaluation.evaluate
```

## Docker

```bash
docker-compose up -d       # Qdrant + API
docker-compose up qdrant -d   # Just Qdrant for local dev
```

After first deploy, run seed once to load canonical fixtures into SQLite + Qdrant:

```bash
docker-compose run --rm api python -m research_agent seed
```

## Testing

- **78 unit tests** covering all modules
- Storage CRUD, embedding, chunking, vector search dedup
- API endpoints, MCP tools, synthesis with mocked LLM
- Connector normalization, sync engine with failure isolation
- Search quality evaluation framework (20+ curated test queries)
