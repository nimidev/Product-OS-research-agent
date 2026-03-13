# Integration Framework Design (US-017)

**Status:** Design (research phase)  
**PRD:** [US-017](../product-docs/research-agent/US-017.md)  
**Audience:** Implementers of the framework and future integration providers

This document defines the integration framework so that every integration (Monday, Jira, and future ones) follows the same API/UI contract and new integrations can be added with minimal duplication.

---

## 1. Adapter vs connector

| Layer | Contract | Responsibility |
|-------|----------|----------------|
| **Integration adapter** | New interface (this framework) | API/UI: config CRUD, schema discovery, test_connection, prepare_sync, auth (OAuth/API key). Used by HTTP routes and the wizard. |
| **Connector** | Existing `BaseConnector` | Sync/ingestion: `list_updated_items`, `normalize_item`, `source_name`, `entity_type`. Used by `SyncEngine` and `_build_connectors`. |

- The **adapter** holds and returns configuration; it does not perform ongoing sync. The **connector** performs sync and normalizes raw API items into `Entity` (with `source_id` and `source_system` for traceability).
- **Wiring:** The adapter’s stored config (e.g. board_ids, entity_configs, field_mappings) is read by the connector factory (e.g. `_build_connectors` in `__main__.py`). The design keeps `Database.get_integration_config(source)` as the single source of truth; adapters read/write via the same storage. Connectors must set `Entity.source_id` and `Entity.source_system` (or equivalent) on every normalized entity.

---

## 2. Adapter interface

All integration adapters implement the following. Types are illustrative; exact signatures live in code.

### 2.1 Core methods

| Method | Purpose | Returns / behavior |
|--------|---------|--------------------|
| `get_config(source_id: str) -> IntegrationConfigResponse` | Return current config for the integration (no secrets in response; use `*_set` booleans). | Generic response shape; source-specific fields in optional payload. |
| `upsert_config(source_id: str, request: IntegrationConfigRequest) -> IntegrationConfigResponse` | Persist config (credentials, entity mappings, scope). | Same response shape; persist via `Database.upsert_integration_config` or equivalent. |
| `get_schema(source_id: str) -> IntegrationSchemaResponse` | Return list of source entities (e.g. boards, projects) and their fields for mapping. | Generic shape: e.g. `{ "scopes": [...], "fields_by_scope": {...} }`. |
| `test_connection(source_id: str) -> TestConnectionResponse` | Verify credentials and connectivity (e.g. call provider API with minimal scope). | `{ "ok": bool, "detail": str }`. |
| `prepare_sync(source_id: str) -> PrepareSyncResponse` | Run a one-off sync/prepare (e.g. fetch, normalize, embed) for the configured scope. | `{ "ok": bool, "fetched", "embedded", "errors", ... }`. |

### 2.2 Auth hooks (optional)

For OAuth-based integrations (e.g. Jira):

| Hook | Purpose |
|------|---------|
| `get_auth_type(source_id: str) -> Literal["oauth", "api_key"]` | So the UI can render the correct auth step. |
| `get_oauth_authorize_url(source_id: str, state: str, redirect_uri: str) -> str` | Return URL to send the user to. |
| `handle_oauth_callback(source_id: str, code: str, state: str) -> None` | Exchange code for tokens, persist in config. |

For API-key integrations (e.g. Monday), the adapter only needs to accept credentials in `upsert_config` and validate them in `test_connection`.

### 2.3 Mapping to existing routes

Current routes stay; they delegate to the adapter for the given `source_id`:

| Current route pattern | Adapter method |
|------------------------|----------------|
| `GET /integrations/{source_id}` | `get_config(source_id)` |
| `PUT /integrations/{source_id}` | `upsert_config(source_id, request)` |
| `GET /integrations/{source_id}/schema` | `get_schema(source_id)` |
| `POST /integrations/{source_id}/test` | `test_connection(source_id)` |
| `POST /integrations/{source_id}/prepare` | `prepare_sync(source_id)` |
| OAuth: `GET .../oauth/authorize`, `GET .../oauth/callback` | Adapter auth hooks (only for OAuth adapters) |

Optional: `POST /integrations/{source_id}/suggest-field-mapping` can remain provider-specific or be added to the interface with a generic request/response.

---

## 3. Auth

| Provider | Auth type | Scopes / notes |
|----------|-----------|----------------|
| **Monday** | API key | Token with board/column read (and write if two-way). |
| **Jira** | OAuth 2.0 (3LO) | `read:jira-work`, `read:jira-user`, `offline_access`. See [JIRA_OAUTH_SETUP.md](JIRA_OAUTH_SETUP.md). |

- The **registry** (see below) exposes `auth_type` per `source_id` so the UI can choose: API key form vs OAuth redirect.
- Credentials are stored only in backend config storage; the adapter never returns raw secrets (only e.g. `api_key_set: true`).

---

## 4. Route strategy

- **Keep existing paths** for backward compatibility: `/integrations/monday`, `/integrations/jira`, etc.
- **Dispatch:** Each route handler loads the adapter from the **registry** by `source_id` and calls the corresponding method. No new generic `GET /integrations/{source_id}` is required initially; existing routes can be refactored to `adapter = registry.get(source_id); return await adapter.get_config()`.
- **Discoverability:** Add a single route if needed, e.g. `GET /integrations` returning `{ "integrations": [ { "source_id": "monday", "auth_type": "api_key" }, { "source_id": "jira", "auth_type": "oauth" } ] }` from the registry, so the UI can list integrations without hardcoding.

---

## 5. Shared config and mapping model

### 5.1 Generic request/response shapes

- **IntegrationConfigRequest** (body for PUT): `enabled`, optional credentials, `entity_mappings` (Product OS entity type → source scope id), `entity_configs` (per-entity field_mappings, direction, etc.). Source-specific fields (e.g. `board_ids`, `cloud_id`, `project_keys`) go into an optional `source_payload: dict`.
- **IntegrationConfigResponse**: Same shape for all integrations: `source`, `enabled`, `*_set` booleans for credentials, `entity_mappings`, `entity_configs`, `updated_at`, optional `source_payload`.
- **EntityMappingConfig**: Shared shape: `entity_type`, `field_mappings` (source_field_id → canonical field name), `direction` (e.g. two_way, source_to_os), plus optional source-specific keys (e.g. `board_ids`, `issue_type_id`).

### 5.2 Storage

- Keep **IntegrationConfigRow** as the single table; it already has `source`, JSON columns for mappings, and optional columns for OAuth/tenant. Adapters serialize/deserialize their source-specific bits into the existing JSON or optional columns so that no schema change is required for backward compatibility.

---

## 6. UI contract

- **Single wizard flow** (onboarding and integration settings):  
  1. Select Product OS entities to sync.  
  2. Authenticate (OAuth redirect or API key form, depending on `auth_type` from registry).  
  3. Select source entity types / scope (boards, projects, issue types — from `get_schema`).  
  4. Field mapping (searchable dropdown for source fields; one shared component for all integrations).  
  5. Test & sync (call `test_connection`, then `prepare_sync`; only then allow “Activate”).

- **Pluggable per integration:**  
  - Auth: component for “API key” vs “OAuth” chosen by `auth_type`.  
  - Schema: one component that renders `get_schema()` result (boards vs projects/issue types) and writes back selected scope into config.

- **Connection status:** Exposed via `get_config` (e.g. `api_key_set`, `oauth_connected`) and/or a small status endpoint; no raw credentials.

- **Empty states:** If `get_schema` returns no items or `test_connection` fails, show clear message and CTA (e.g. re-authenticate, check permissions). Mapping cannot be activated until test succeeds.

---

## 7. Sync model

- **Default:** Pull/sync (polling) only. The SyncEngine and `BaseConnector.list_updated_items` remain the mechanism; no change to sync semantics in this design.
- **Webhooks / push:** Out of scope for the framework; can be added per integration later if the provider supports it.

---

## 8. Traceability

- Every **connector** (sync layer) must set on each normalized `Entity`:
  - `source_id`: stable id in the source system (e.g. Jira issue key, Monday item id).
  - `source_system`: e.g. `SourceSystem.JIRA`, `SourceSystem.MONDAY` (or equivalent string).
- The framework design doc and the “new integration” checklist require this so that search and citations can attribute results to the correct source.

---

## 9. Implementation order (for US-017)

1. **Design doc** (this document) — done.
2. **Adapter interface + registry** — Define the Python interface and a registry (e.g. `IntegrationAdapterRegistry.register(source_id, adapter)`); implement only the registry and types; no route changes yet.
3. **Unified config/mapping models** — Introduce Pydantic models `IntegrationConfigRequest`, `IntegrationConfigResponse`, `EntityMappingConfig` with `source` discriminator and optional `source_payload`; keep existing DB shape.
4. **Migrate Monday** — Implement adapter for Monday; refactor existing Monday routes to call the adapter; preserve behavior.
5. **Migrate Jira** — Implement adapter for Jira; refactor existing Jira routes (including OAuth) to call the adapter; preserve behavior.
6. **Wizard + shared field-mapping UX** — One wizard, shared searchable-dropdown component; pluggable auth and schema loaders (implementation may live in a separate repo if UI is split).
7. **Contract tests** — Per-adapter tests with mocked provider APIs for get_config, get_schema, test_connection, prepare_sync.
8. **New-integration checklist** — Short doc: implement adapter, register, add to UI list and wizard; reference this design and traceability.

---

## 10. References

- [US-017 PRD](../product-docs/research-agent/US-017.md)
- product-os-integrations-architect agent (Adapter Pattern, contract tests, auth, traceability)
- Existing: `research_agent/connectors/base.py` (BaseConnector), `research_agent/api/server.py` (Monday/Jira routes), `research_agent/storage/db.py` (get/upsert_integration_config), `research_agent/storage/models.py` (Entity, IntegrationConfigRow)
