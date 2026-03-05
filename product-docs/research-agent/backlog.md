# research-agent - Backlog

| ID | Title | Status | Priority | Phase |
|----|-------|--------|----------|-------|
| [US-001](./US-001.md) | Research Agent – AI-Powered Organizational Knowledge Search | done | P0 | development |
| [US-002](./US-002.md) | Migrate to Canonical Entity Model | done | P0 | planning |
| [US-003](./US-003.md) | Product OS UI and Integration Service (Phase 1 – Monday.com) | done | P0 | planning |
| [US-004](./US-004.md) | Product Context Sidebar (Future) | backlog | P2 | planning |
| [US-005](./US-005.md) | Chat Response Entity Labels (Future) | backlog | P2 | planning |
| [US-006](./US-006.md) | Suggested Next Question (Future) | backlog | P2 | planning |
| [US-007](./US-007.md) | Entity and Field Mapping for Integrations (Connect → Map → Sync) | create | P0 | planning |
| [US-008](./US-008.md) | Research Agent – Pro Product Researcher Chat Experience | done | P1 | deployed |
| [US-009](./US-009.md) | Integrations Page – View vs Edit UX Redesign | done | P1 | deployed |
| [US-010](./US-010.md) | Research Agent – Clickable Evidence References in Chat | done | P1 | deployed |
| [US-011](./US-011.md) | Seamless Onboarding & Setup Experience for New Users | done | P0 | deployed |
| [US-012](./US-012.md) | Backlog Integration – Jira & Confluence (Atlassian) | create | P1 | planning |
| [US-013](./US-013.md) | Backlog Integration – Mixpanel (Product Analytics) | create | P1 | planning |
| [US-014](./US-014.md) | Backlog Integration – Gong (Revenue Intelligence / Calls) | create | P1 | planning |
| [US-015](./US-015.md) | Backlog Integration – SharePoint (Microsoft 365) | create | P1 | planning |
| [US-016](./US-016.md) | Backlog Integration – Productboard (Product Management) | create | P1 | planning |

### US-007: Entity and Field Mapping for Integrations (Connect → Map → Sync)
- **Status**: `create`
- **Description**: Guided mapping of Product OS entities to integration entities/fields (e.g. Monday Epics, Tasks, Bugs, Support); link to boards, map fields, set sync direction, review & test before activate.
- **See**: [US-007.md](./US-007.md)
- **Branch**: (not yet created)

### US-008: Research Agent – Pro Product Researcher Chat Experience
- **Status**: `done`
- **Description**: Upgrade the chat experience so the Research Agent behaves like a professional product researcher: runs high-quality product research, leverages entity data, applies product research frameworks, and delivers both bottom-line conclusions and deep-dive analysis tailored to the organization.
- **See**: [US-008.md](./US-008.md)
- **Branch**: `feature/US-008-pro-researcher-chat` (merged to main)

### US-009: Integrations Page – View vs Edit UX Redesign
- **Status**: `done`
- **Description**: Redesign the Integrations page to clearly show which integrations and entities are active (e.g. Support, Bugs, Feature Requests) and separate read-only “View” mode from a guided “Edit” mode for configuring entities and field mappings.
- **See**: [US-009.md](./US-009.md)
- **Branch**: `feature/US-009-integrations-view-edit-ux` (merged to main)

### US-010: Research Agent – Clickable Evidence References in Chat
- **Status**: `done`
- **Description**: Update the Research Agent chat experience so that every evidence reference (e.g. “[8, 17]” after “Bugs: Highlight reliability problems with the API”) is rendered as a clear, clickable citation that maps to specific entities or documents, with an obvious way to inspect what each reference points to.
- **See**: [US-010.md](./US-010.md)
- **Branch**: `feature/US-010-clickable-evidence-refs` (merged to main)

### US-011: Seamless Onboarding & Setup Experience for New Users
- **Status**: `done`
- **Description**: Define and build a frictionless onboarding/setup/configuration flow for new users cloning the repo, covering dependency handling (Docker/Qdrant), environment configuration, health checks, and guided setup wizard to achieve high completion rates.
- **See**: [US-011.md](./US-011.md)
- **Branch**: `feature/US-011-seamless-onboarding` (merged to main)
- **PR**: #6 (merged)
- **Testing**: ✅ All tests passed

### US-012: Backlog Integration – Jira & Confluence (Atlassian)
- **Status**: `create`
- **Description**: Dedicated integration for Atlassian Cloud: OAuth 2.0, map Jira projects/issue types and Confluence spaces to Product OS entities (epic, task, bug, feature_request, support_ticket, document/PRD), sync and search with citations.
- **See**: [US-012.md](./US-012.md)
- **Branch**: (not yet created)

### US-013: Backlog Integration – Mixpanel (Product Analytics)
- **Status**: `create`
- **Description**: Dedicated integration for Mixpanel: project token auth, configurable event/export scope, map to Product OS analytics entity types, sync and expose product usage evidence in Research Agent search and chat.
- **See**: [US-013.md](./US-013.md)
- **Branch**: (not yet created)

### US-014: Backlog Integration – Gong (Revenue Intelligence / Calls)
- **Status**: `create`
- **Description**: Dedicated integration for Gong: API key auth, call listing and transcript fetch, map calls/transcripts to meeting_note or customer_call entities, sync and search with citations to Gong call URLs.
- **See**: [US-014.md](./US-014.md)
- **Branch**: (not yet created)

### US-015: Backlog Integration – SharePoint (Microsoft 365)
- **Status**: `create`
- **Description**: Dedicated integration for SharePoint via Microsoft Graph: Azure AD auth, site/list/library selection, map documents and list items to Product OS entity types, sync and search with citations to SharePoint URLs.
- **See**: [US-015.md](./US-015.md)
- **Branch**: (not yet created)

### US-016: Backlog Integration – Productboard (Product Management)
- **Status**: `create`
- **Description**: Dedicated integration for Productboard: API token or OAuth2, map features, ideas, notes, roadmap to Product OS entity types (feature_request, roadmap_item, prd, etc.), sync and search with citations to Productboard.
- **See**: [US-016.md](./US-016.md)
- **Branch**: (not yet created)

<!-- Stories are added automatically by the /create command in Cursor -->
