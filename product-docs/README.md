# Product OS Research Agent

Product documentation workspace for the Research Agent service.

## Projects

| Project | Description |
|---------|-------------|
| [research-agent](./research-agent/) | AI-powered organizational knowledge search service |

Each project may have a **`context/`** folder. All Product OS commands (`/create`, `/dev`, `/release`, `/verify`) read from it when present:

- **`context/PROJECT_CONTEXT.md`** — Product, users, repo, common non-goals (avoids repeating project-level questions in `/create`).
- **`context/TECH_CONTEXT.md`** — Technical stack, conventions, and standards (replaces per-repo `RULES.md` for Product OS).

## Story ID Registry

**Next Available ID: US-018**

When creating a new story, use the next available ID.

## Quick Start

- Create a story: `/create "feature description" @research-agent/backlog.md`
- Develop: `/dev US-{ID}`
- Release: `/release US-{ID}`
