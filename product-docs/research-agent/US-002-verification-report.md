# PRD Verification Report: US-002

**Story:** Migrate to Canonical Entity Model  
**PRD:** [US-002.md](./US-002.md)  
**Verified:** 2026-02-21

---

## Overall Score: 8/10

## Summary

- **Passed:** 18 checks
- **Gaps:** 4 items (0 high, 2 medium, 2 low)
- **Readiness:** **Ready for dev** (with optional improvements)

---

## Strengths

1. **Problem statement** is clear: flat schema loses field semantics, no field-aware search, per-tool code changes.
2. **Acceptance criteria** are numbered (AC1–AC9), testable, and specific (no "should/might").
3. **Re-ingest decision** is explicit and simplifies scope (no migration, no dual-write).
4. **Canonical model** is fully specified (6 entities, exact fields, 3 tables).
5. **Non-goals** and **success metrics** are explicit.
6. **Test strategy** is concrete (seed, field-aware search, config remap, integration).
7. **RULES.md alignment:** PRD fits Python, SQLAlchemy, Qdrant, config, pytest; no conflicts.

---

## High priority gaps

*None.*

---

## Medium priority gaps

### Gap 1: Target users not explicit

**Issue:** Problem statement says "PMs cannot search by field" but there is no dedicated "Target Users" or "Who benefits" line. Slight risk of scope creep or unclear prioritization.

**Suggested fix:** Add a short line under Problem Statement or in Metadata:

```markdown
## Target Users

Product managers and teams using the Research Agent to search organizational knowledge; operators who configure Monday/Notion (and future) connectors via YAML.
```

---

### Gap 2: Edge cases and error handling

**Issue:** PRD does not state behavior for: empty search results, malformed fixture rows, invalid or missing mapping config, connector failure during sync. RULES.md says "never crash on bad input — log, skip, or degrade gracefully."

**Suggested fix:** Add a short "Edge Cases & Errors" subsection under NFRs or before Test Strategy:

```markdown
## Edge Cases & Error Handling

- **Empty search:** Returns empty list with no error (consistent with existing behavior).
- **Malformed fixture:** Seed logs error for the row, skips it, continues (no crash).
- **Invalid mapping config:** Sync/seed fails fast with clear error (e.g. "Unknown field in mapping: X").
- **Connector failure (Monday/Notion):** Isolated per connector; other sources continue; failed source logged and retried next run.
```

---

## Low priority / suggestions

### 1. Content hashing for canonical model

**Issue:** RULES.md specifies content hashing for change detection. PRD does not say how hashing works for entities (e.g. hash per entity from all field values, or per field for chunk invalidation).

**Suggestion:** During dev, define and document: e.g. "content_hash on entity = hash of concatenated field values" or "per chunk" so sync/seed can skip unchanged entities. No PRD change required if captured in schema.md or code comments.

### 2. Dev tasks placeholder

**Issue:** Dev Tasks say "To be generated after requirements are clear and features extracted."

**Suggestion:** Optional one-liner to guide extraction: "Dev tasks will cover: new schema (entities/entity_fields/chunks), fixture reshape to canonical fields, seed rewrite, connector normalize + mapping config, field-aware search, README/config examples."

---

## Optional: All six entity types

AC3 and AC4 call out feature_request and meeting_note only. The canonical model defines 6 types. If you want an explicit guarantee that all 6 are supported for ingest and search, add:

- **AC10** – All six entity types (feature_request, roadmap_item, support_ticket, bug, prd, meeting_note) can be ingested from fixtures or connectors and returned by search when filtered by `entity_types`.

Otherwise, "all 6" can remain implied by the canonical model table and connector pattern.

---

## Recommended actions

1. **Optional:** Add "Target Users" line (medium gap 1).
2. **Optional:** Add "Edge Cases & Error Handling" subsection (medium gap 2).
3. Proceed to feature extraction and dev; address content-hash and dev-task detail during implementation if needed.

---

## Options

- **`apply all`** – Add Target Users + Edge Cases (and optional AC10) to US-002.md.
- **`apply high`** – No high-priority fixes (none identified).
- **`manual`** – You edit the PRD yourself.
- **`approve anyway`** – Proceed without changes (PRD already in good shape).

---

**Next steps**

- If ready: `/dev US-002` or run story-create Phase 4 (extract features, then `/dev`).
- If you apply fixes: run `/verify US-002` again to confirm.
