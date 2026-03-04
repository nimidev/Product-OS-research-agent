# Upgrading Qdrant: Local Mode → Docker Server

When your data grows beyond ~20,000 vectors, the built-in local storage mode
may slow down. Upgrading to a Qdrant Docker server gives you production-grade
performance with no data loss.

## Prerequisites

- Docker installed ([docker.com](https://www.docker.com/products/docker-desktop/))
- Docker Desktop running

## Steps

### 1. Start Qdrant server

```bash
docker-compose up qdrant -d
```

This pulls the Qdrant image and starts it on ports 6333/6334.

### 2. Update your `.env`

```env
QDRANT_MODE=server
QDRANT_HOST=localhost
QDRANT_PORT=6333
```

### 3. Migrate your vectors

```bash
python -m research_agent reindex
```

This reads all entities from your local SQLite database, re-embeds them,
and writes the vectors to the Qdrant server. Depending on data size, this
may take a few minutes.

### 4. Restart the API

```bash
python -m research_agent serve
```

### 5. Verify

```bash
python -m research_agent doctor
```

You should see: `Qdrant accessible (server mode) — X vectors`.

## Qdrant Cloud (alternative)

Instead of running Docker locally, you can use [Qdrant Cloud](https://cloud.qdrant.io/)
with a free tier:

1. Create a cluster at cloud.qdrant.io
2. Set `QDRANT_MODE=server`, `QDRANT_HOST=<your-cluster>.cloud.qdrant.io`,
   `QDRANT_PORT=6333` in `.env`
3. Run `python -m research_agent reindex`
4. Restart the API

## Rollback

To go back to local mode:

```env
QDRANT_MODE=local
```

Your local data in `./qdrant_data` is preserved and will be used again.
