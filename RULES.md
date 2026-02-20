# Research Agent — Technical Standards

## Language & Runtime

- Python 3.11+
- Async-first where applicable (FastAPI is async)
- Type hints on all public functions and class attributes

## Code Quality

- Formatter: `ruff format`
- Linter: `ruff check`
- Type checking: `mypy --strict`
- Line length: 100 characters

## Dependencies

- **API**: FastAPI + Uvicorn
- **Database**: SQLAlchemy + SQLite (aiosqlite for async)
- **Vector DB**: Qdrant (via qdrant-client)
- **Embeddings**: OpenAI text-embedding-3-small (behind EmbeddingProvider interface)
- **LLM**: OpenAI GPT-4o-mini for synthesis (behind configurable provider)
- **MCP**: Official MCP Python SDK (stdio transport)
- **Config**: pydantic-settings + python-dotenv for .env

## Project Structure

- Main package: `research_agent/`
- One module per concern (storage, vector, embedding, memory, synthesis, api, mcp, config)
- Pydantic models for all data transfer objects
- SQLAlchemy models for database entities

## Patterns

- Dependency injection via function parameters, not module-level globals
- All config via environment variables (Phase 1) or config.yaml (Phase 2+)
- Structured logging: `structlog` or stdlib logging with JSON formatter
- Error handling: never crash on bad input — log, skip, or degrade gracefully
- Content hashing for change detection: `hashlib.sha256(title + body)`

## Testing

- Framework: pytest + pytest-asyncio
- Test files: `tests/test_*.py`
- Shared fixtures: `tests/conftest.py`
- Mock all external APIs (OpenAI, Qdrant) in unit tests
- Integration tests use Qdrant in Docker

## Git

- Branch naming: `feature/US-{ID}-{slug}`
- Commit messages: imperative mood, reference task number
- No secrets in commits — `.env` is gitignored
