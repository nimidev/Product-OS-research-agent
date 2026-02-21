# PRD Verification Report: US-002

**Story:** Migrate to Canonical Entity Model  
**PRD:** [US-002.md](./US-002.md)  
**Verified:** 2026-02-21

---

## Overall Score: 8.5/10

## Summary

- **Passed:** 22 checks
- **Gaps:** 2 items (0 high, 0 medium, 2 low)
- **Readiness:** **Ready for dev**

---

## Strengths

1. **Problem statement** is clear: flat schema loses field semantics, no field-aware search, per-tool code changes; flexible search UX called out in Goal.
2. **Target users** explicit: PMs and operators configuring connectors.
3. **Acceptance criteria** numbered (AC1–AC12), testable, and specific; no vague "should/might."
4. **Flexible search** fully specified: default = search all when no filters; AC12 requires the system to determine entity/field scope from question and context; implementation can live in service or MCP/caller; test strategy includes flexible search tests.
5. **Canonical model** fully defined: 6 entities, exact fields, 3 tables.
6. **Edge cases & error handling** covered: empty search, malformed fixture, invalid mapping, connector failure.
7. **Non-goals** and **success metrics** explicit; re-ingest strategy and config-driven mapping clear.
8. **RULES.md alignment:** PRD fits Python, SQLAlchemy, Qdrant, config, pytest; edge-case behavior aligns with "never crash — log, skip, degrade gracefully."

---

## High Priority Gaps

*None.*

---

## Medium Priority Gaps

*None.*

---

## Low Priority / Suggestions

### 1. Query-understanding fallback

**Issue:** When query/context inference fails or is unavailable (e.g. LLM down, ambiguous query), the PRD implies "search all" but does not state it explicitly.

**Suggestion:** Optional one-liner in Edge Cases or Architecture: "When query/context inference cannot determine scope (e.g. ambiguous question or inference unavailable), search falls back to all entity types and searchable fields." Not required for readiness; improves clarity.

### 2. Content hashing in new schema

**Issue:** RULES.md specifies content hashing for change detection (title + body). The new model uses entities + entity_fields + chunks; how hashing works (per-entity, per-field, or per-chunk) is not defined in the PRD.

**Suggestion:** Leave to implementation/schema doc. If desired, add to NFRs or Architecture: "Change detection for sync/seed uses a content hash (e.g. per entity from field values or per chunk) so unchanged data is not re-embedded." Low priority.

---

## Recommended Actions

1. Proceed to dev; no blocking gaps.
2. Optionally add the inference-fallback sentence for clarity.
3. Define content-hash strategy during implementation and document in schema or code.

---

## Options

- **`apply all`** – Add the optional inference-fallback line to Edge Cases or Architecture.
- **`apply high`** – No high-priority fixes (none identified).
- **`manual`** – You edit the PRD yourself.
- **`approve anyway`** – Proceed as-is (PRD is ready for dev).

---

**Next steps**

- If ready: `/dev US-002` or run story-create Phase 4 (extract features, then `/dev`).
- If you apply the optional fix: run `/verify US-002` again to confirm.
