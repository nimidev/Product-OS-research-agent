#!/usr/bin/env python3
"""
Generate JIRA-importable CSV mock data for Product OS / Research Agent demo.

Output: three CSVs (stories, tasks, bugs) with Summary, Description, Status, Priority, Labels, Created, Updated.
Work type is implied by filename. Use JIRA Cloud: Import each CSV and map Work type in UI if needed.
Run once then delete this script per project convention.

Usage:
  python scripts/generate_jira_mock_csv.py [--output-dir dir] [--per-type N]
  Default: --output-dir . --per-type 50
  Writes: jira_mock_stories.csv, jira_mock_tasks.csv, jira_mock_bugs.csv
"""

from __future__ import annotations

import argparse
import csv
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path


def _random_date(start: datetime, end: datetime) -> datetime:
    delta = end - start
    return start + timedelta(seconds=random.randint(0, int(delta.total_seconds())))


def _fmt_dt(dt: datetime) -> str:
    """JIRA system date time format per Atlassian docs."""
    return dt.strftime("%Y-%m-%d %H:%M:%S")


# --- Story titles & descriptions (Product OS / Research Agent / Jira demo) ---
STORY_ITEMS = [
    ("Search across Jira and research memories", "As a PM I want to run a single query and see results from both Jira issues and the research agent memory so I can make decisions without switching tools."),
    ("Onboarding wizard for Jira OAuth", "As an admin I want to connect Jira via OAuth in the onboarding wizard so the research agent can sync issues without API keys."),
    ("Map Jira fields to canonical product OS fields", "As an admin I want to map Jira summary, status, priority to our canonical schema so search and reports use consistent field names."),
    ("Sync Jira backlog and sprint issues", "As a team lead I want the research agent to sync both backlog and active sprint so our board state is searchable."),
    ("Filter search by Jira project and issue type", "As a user I want to filter by project key and issue type (Story, Bug, Task) so I can narrow results to relevant work."),
    ("Real-time collaboration engine", "As a user I want to see live updates when teammates edit so we can collaborate on research and PRDs in real time."),
    ("Custom instructions per research context", "As a researcher I want different default instructions for product vs engineering research so context stays relevant."),
    ("Conversation folders and organization", "As a user I want to organize research conversations into folders by product area so I can find past analysis quickly."),
    ("Search within my conversations", "As a user I want full-text search over my past research chats so I can reuse prior findings."),
    ("Export research to Markdown or PDF", "As a PM I want to export a research summary to Markdown or PDF for stakeholders who do not use the tool."),
    ("Longer context window for PRD ingestion", "As a user I want to paste long PRDs and have the agent use full context so nothing is truncated."),
    ("Better code execution and debugging", "As an engineer I want the research agent to run and debug code snippets when analyzing technical specs."),
    ("Enterprise data privacy and residency", "As an enterprise admin I want research data to stay in our region and not be used for model training."),
    ("Team workspaces and shared research", "As a team I want a shared workspace where we can pool research and link to Jira epics."),
    ("Memory that persists across sessions", "As a user I want the research agent to remember key facts and preferences so I do not repeat myself."),
    ("Voice mode for research summaries", "As a PM I want to hear a short voice summary of top insights when I am on the go."),
    ("Custom connector discoverability", "As an admin I want to discover and enable Jira, Monday, Zoom connectors from a single place."),
    ("API rate limits and usage dashboard", "As an admin I want to see embedding and LLM usage so I can control cost and quotas."),
    ("Conversation branching", "As a user I want to branch a conversation and try different prompts without losing the original thread."),
    ("Mobile app parity for search", "As a user I want to run research queries from mobile with the same filters as desktop."),
    ("Embedding quality and model choice", "As an admin I want to choose embedding model and see quality metrics for search relevance."),
    ("Scheduled and recurring research digests", "As a PM I want a weekly digest of new Jira issues and research highlights in my inbox."),
    ("Jira issue type mapping in onboarding", "As an admin I want to map Story/Bug/Task to our entity types during onboarding so sync is correct."),
    ("Board and sprint selector for Jira", "As an admin I want to pick a board and optionally a sprint so we only sync relevant issues."),
    ("Incremental Jira sync by updated date", "As a user I want only recently updated issues to be synced so imports are fast and fresh."),
    ("Link research items to Jira issues", "As a user I want to attach a research note or PRD to a Jira issue for traceability."),
    ("Unified search across Jira and Monday", "As a PM I want one query to search both Jira and Monday so I see all work in one view."),
    ("Research agent health and sync status", "As an admin I want to see connector health and last sync time so I can fix broken integrations."),
    ("Scoped search by source", "As a user I want to restrict search to Jira only or research memory only when I know the source."),
    ("Chunking strategy for long descriptions", "As an admin I want to tune how long Jira descriptions are chunked for embedding quality."),
    ("Story points and epic link in sync", "As a team we want story points and epic link synced so velocity and hierarchy are searchable."),
    ("OAuth token refresh for Jira", "As an admin I want the app to refresh Jira OAuth tokens so sync continues without re-auth."),
    ("Bulk import historical Jira data", "As an admin I want to one-time import a large Jira export so we have history in the research agent."),
    ("Search filters by priority and status", "As a user I want to filter by Jira priority and status so I can focus on high-priority open items."),
    ("Deduplication of similar issues in search", "As a user I want the research agent to collapse near-duplicate Jira issues in results."),
    ("Research suggestions from Jira context", "As a user I want the agent to suggest related research when I open a Jira issue."),
    ("Audit log for sync and embeddings", "As an enterprise admin I want an audit log of what was synced and when for compliance."),
    ("Multi-project Jira sync", "As an admin I want to sync multiple Jira projects into one research space with separate field mappings."),
    ("Default assignee and reporter in import", "As an admin I want to map CSV assignee/reporter by email when importing so ownership is clear."),
    ("Rich text and ADF in Jira description", "As a user I want Jira descriptions with formatting and links to render correctly in search snippets."),
    ("Search ranking by relevance and recency", "As a user I want results ordered by both relevance and last updated so important recent work surfaces."),
    ("Offline cache of recent search results", "As a user I want recently viewed results cached offline so I can read without network."),
    ("Keyboard shortcuts for search", "As a power user I want keyboard shortcuts to open search and jump to first result."),
    ("Bulk actions on search results", "As a PM I want to select multiple results and export or add to a board in one action."),
    ("Templates for research questions", "As a team we want saved templates for common queries (e.g. open bugs by component) to run quickly."),
    ("Slack notification for high-priority Jira", "As a PM I want a Slack message when a new high-priority issue matches a saved filter."),
    ("CSV export of search results", "As a user I want to export current search results to CSV for reporting."),
    ("Dark mode for research UI", "As a user I want dark mode so I can use the research agent in low light."),
    ("Accessibility and screen reader support", "As a user I need full keyboard and screen reader support for the research UI."),
    ("Localization of UI and date formats", "As an international user I want UI and dates in my locale."),
    ("Feedback button on search results", "As a user I want to mark a result as helpful or not to improve ranking over time."),
    ("Saved searches and alerts", "As a user I want to save a search and get notified when new items match."),
    ("Unified backlog view across Jira projects", "As a PM I want one backlog view that aggregates multiple Jira projects with filters."),
]

# --- Task titles & descriptions (implementation work) ---
TASK_ITEMS = [
    ("Implement Jira OAuth callback handler", "Handle redirect from Atlassian, exchange code for tokens, store refresh token securely."),
    ("Add Jira project and board discovery API", "Call Jira REST for projects and Agile API for boards; expose in onboarding UI."),
    ("Map Jira field IDs to canonical names", "Use Jira Fields API to list fields; allow admin to map summary, description, status, priority."),
    ("Implement incremental sync with updated >= date", "JQL filter by updated; paginate and normalize to Entity model."),
    ("Write chunking logic for Jira description ADF", "Parse ADF, extract plain text, chunk for embedding with configurable size."),
    ("Add Story points and Epic link to field mapping", "Support custom fields for story points and parent epic in connector."),
    ("Implement token refresh before sync", "Check expiry, use refresh_token to get new access_token before each sync run."),
    ("Add health check endpoint for Jira connector", "Call accessible-resources or project list; return ok/fail for UI."),
    ("Unit tests for Jira connector with mocked API", "Mock httpx responses for search, project, fields; assert Entity output."),
    ("Integration test with test Jira instance", "Optional test that runs against a real test project if env vars set."),
    ("Document Jira OAuth app setup in Confluence", "Step-by-step: create app, callback URL, scopes, env vars."),
    ("Add Jira issue type selector in onboarding", "Dropdown of issue types from project; multi-select for Story, Bug, Task."),
    ("Implement backlog and sprint fetch via Agile API", "Board backlog and sprint issue endpoints; filter by issue type."),
    ("Add Created and Updated to CSV export", "Include system dates in CSV for Jira import compatibility."),
    ("Validate CSV encoding and quoting for Jira import", "Ensure UTF-8 and double-quote escaping per Atlassian CSV spec."),
    ("Add Labels column to Jira sync mapping", "Optional mapping of Jira labels to canonical labels or tags."),
    ("Implement delete detection for Jira issues", "Compare last sync keys with current JQL result set; mark removed as deleted."),
    ("Add rate limit backoff and retry for Jira API", "On 429, respect Retry-After and exponential backoff."),
    ("Log sync stats (created, updated, deleted) per run", "Structured log or metric for observability."),
    ("Add optional Reporter and Assignee to sync", "Map by account ID or email; store in entity fields if configured."),
    ("Implement search filter by source = jira", "Pass source filter to vector store and entity store."),
    ("Add project key filter to Jira sync config", "Allow restricting to single project or list of projects."),
    ("UI: connector card for Jira with status and last sync", "Show connected project, last sync time, health; link to settings."),
    ("UI: field mapping table with drag-drop order", "Table of Jira field -> canonical field; reorder to control chunking priority."),
    ("Backend: store field_mappings per connector config", "Persist in DB or config so mappings survive restart."),
    ("Add description preview in search results", "Show first 200 chars of description in result card."),
    ("Implement pagination for search results", "Cursor or offset pagination for large result sets."),
    ("Add sort by relevance and sort by updated", "Toggle in UI; pass to search API."),
    ("E2E test: onboarding -> Jira connect -> first sync", "Playwright or similar; run in CI with test Jira."),
    ("Add API key validation for OpenAI in onboarding", "Call OpenAI with test prompt; show success or error."),
    ("Implement Qdrant collection init in setup wizard", "Create collection with correct dimension from embedding model."),
    ("Add doctor command for Jira connector", "Check token validity, project access, and last successful sync."),
    ("Document required Jira OAuth scopes", "List read:jira-work, read:jira-user, offline_access and why."),
    ("Add Work type column to generated CSV", "Column values Story, Task, Bug for Jira import mapping."),
    ("Generate 50 items per type in mock CSV script", "Stories, Tasks, Bugs with Product OS themed titles and descriptions."),
    ("Validate Summary length <= 255 for Jira", "Truncate or warn if summary exceeds Jira limit."),
    ("Add Status and Priority to mock data", "Vary status (To Do, In Progress, Done) and priority (High, Medium, Low)."),
    ("Add Created and Updated timestamps to mock CSV", "Spread dates over past 6 months for realistic distribution."),
    ("Implement batch embedding for large syncs", "Chunk entities into batches of 100 for embedding API calls."),
    ("Add progress indicator for sync in UI", "Show current step and entity count during Jira sync."),
    ("Implement cancel button for running sync", "Set flag or task ID so sync loop exits gracefully."),
    ("Add sync schedule configuration", "Optional cron or interval for automatic Jira sync."),
    ("Store last_sync_at and last_sync_error in DB", "Per connector; show in UI and use for incremental sync."),
    ("Add Labels to mock CSV generator", "Product-OS, research-agent, demo, jira-sync, etc."),
    ("Write README section for Jira demo data", "How to run script, import CSV in Jira, and connect research agent."),
    ("Add optional Parent column for hierarchy in CSV", "Work item ID and Parent for epics and stories."),
    ("Test import with Jira Cloud trial", "Run full import in a trial site and verify search works."),
]

# --- Bug titles & descriptions ---
BUG_ITEMS = [
    ("Jira sync fails with 401 after token expiry", "OAuth access token expires; sync returns 401. Refresh token flow must run before sync."),
    ("Memory not retaining research context", "Research agent fails to recall facts that were explicitly saved. Affects embedding and retrieval path."),
    ("Search returns no results after Jira sync", "Vector upsert or entity store not updated; or project filter too strict."),
    ("Onboarding wizard stuck on Jira OAuth step", "Callback URL mismatch or state param lost; user redirected but wizard does not advance."),
    ("Jira description truncated in search snippet", "ADF extraction or chunking cuts off mid-sentence; need larger chunk or smarter boundary."),
    ("Duplicate issues in search results", "Same Jira issue appears multiple times; dedupe by issue key in store or vector metadata."),
    ("Embedding call rate limit during bulk sync", "OpenAI 429 when syncing large project; need backoff and batch sizing."),
    ("Field mapping lost after server restart", "Field mappings not persisted; only in memory. Save to config or DB."),
    ("Jira board list empty for valid project", "Agile API scope or project key filter wrong; boards not returned."),
    ("Priority and status show as raw IDs", "Jira returns priority/status as objects; extract name for display and mapping."),
    ("CSV import fails with comma in description", "Description not quoted or quotes not escaped; Jira CSV import rejects row."),
    ("Search latency over 2s for 10k issues", "Vector search or embedding batch too large; optimize index or batching."),
    ("Jira OAuth callback 400 invalid_grant", "Refresh token expired or revoked; need to re-auth and surface clear error."),
    ("Chunks from same issue not linked", "Parent ID or issue key missing in vector payload; cannot group by issue."),
    ("Incremental sync re-imports all issues", "Updated filter not applied or stored; full scan every time."),
    ("UI shows success but no issues in project", "Sync reported ok but JQL returned 0; log JQL and response for debug."),
    ("Assignee and reporter show as account IDs", "Need to resolve account ID to display name or email for UI."),
    ("Story points not synced", "Custom field ID for story points not in mapping or not requested in JQL fields."),
    ("Epic link broken in search result", "Parent key or epic link field not extracted; hierarchy lost."),
    ("Labels with comma break CSV export", "Labels must be quoted or split into multiple columns per Jira import spec."),
    ("Sync deletes issues still present in Jira", "Delete detection logic wrong; comparing wrong set or race condition."),
    ("Research agent returns wrong source", "Source filter not passed or entity source_system incorrect."),
    ("Embedding dimension mismatch after model change", "Collection created with old dimension; need migration or recreate."),
    ("Jira 429 Retry-After not respected", "Parser or sleep logic wrong; still hitting rate limit."),
    ("Onboarding fails when OpenAI key missing", "Wizard should validate key before Jira step; clear error message."),
    ("Search filters ignored for Jira source", "Filter by status/priority not applied in JQL or post-filter."),
    ("Created date in wrong timezone in CSV", "Use UTC or explicit timezone so Jira import shows correct date."),
    ("Long summary truncated without warning", "Jira Summary 255 char limit; truncate and add ellipsis or warn in script."),
    ("Backlog fetch returns only first 50 issues", "Pagination not implemented; loop until no more results."),
    ("Sprint selector shows closed sprints", "Filter to open or future sprints only in dropdown."),
    ("Multiple connectors overwrite same entity ID", "Entity ID must include source and project; e.g. jira:PROJ-123."),
    ("Qdrant upsert fails for large batch", "Batch size too large; split into smaller batches."),
    ("Health check false positive when project deleted", "Token valid but project removed; check project exists."),
    ("Field mapping UI does not show custom fields", "Fetch fields from Jira Fields API and include custom in list."),
    ("Sync state key collision for two projects", "sync_state_key must include project key; two projects shared state."),
    ("Description ADF with table renders empty", "ADF table extraction not implemented; fall back to raw or table text."),
    ("Search by exact key (e.g. PROJ-123) returns nothing", "Issue key not in title or chunk text; add key to searchable content."),
    ("Mock data script generates duplicate summaries", "Add suffix or index to make each row unique for import."),
    ("Import fails on first row with special characters", "Escape double quotes and newlines in all string fields."),
    ("Jira Cloud ID not saved after OAuth", "Cloud ID from accessible-resources must be stored for API base URL."),
    ("Refresh token not persisted", "Store refresh_token in secure config; only access_token in memory."),
    ("Sync runs twice on startup", "No guard against concurrent sync; use lock or single runner."),
    ("Search result link to Jira 404", "Base URL or issue key wrong; build correct Jira browse URL."),
    ("Labels column empty in generated CSV", "Script must output Labels for a subset of rows for testing."),
]

STATUSES = ["To Do", "In Progress", "Done", "To Do", "In Progress"]  # weight open
PRIORITIES = ["Highest", "High", "Medium", "Low", "Lowest"]
LABELS_POOL = ["product-os", "research-agent", "jira", "demo", "onboarding", "search", "sync", "embeddings", "backend", "frontend", "docs"]


def _pick_labels() -> str:
    return " ".join(random.sample(LABELS_POOL, k=random.randint(1, 4)))


def _random_date_range(days_back: int = 180) -> tuple[datetime, datetime]:
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days_back)
    return start, end


def generate_stories(n: int, start: datetime, end: datetime) -> list[dict]:
    rows = []
    pool = list(STORY_ITEMS)
    for i in range(n):
        title, desc = pool[i % len(pool)]
        if i >= len(pool):
            title = f"{title} (variant {i + 1})"
        created = _random_date(start, end)
        updated = _random_date(created, end)
        rows.append({
            "Summary": title[:255],
            "Description": desc,
            "Status": random.choice(STATUSES),
            "Priority": random.choice(PRIORITIES),
            "Labels": _pick_labels(),
            "Created": _fmt_dt(created),
            "Updated": _fmt_dt(updated),
        })
    return rows


def generate_tasks(n: int, start: datetime, end: datetime) -> list[dict]:
    rows = []
    pool = list(TASK_ITEMS)
    for i in range(n):
        title, desc = pool[i % len(pool)]
        if i >= len(pool):
            title = f"{title} ({i + 1})"
        created = _random_date(start, end)
        updated = _random_date(created, end)
        rows.append({
            "Summary": title[:255],
            "Description": desc,
            "Status": random.choice(STATUSES),
            "Priority": random.choice(PRIORITIES),
            "Labels": _pick_labels(),
            "Created": _fmt_dt(created),
            "Updated": _fmt_dt(updated),
        })
    return rows


def generate_bugs(n: int, start: datetime, end: datetime) -> list[dict]:
    rows = []
    pool = list(BUG_ITEMS)
    for i in range(n):
        title, desc = pool[i % len(pool)]
        if i >= len(pool):
            title = f"{title} ({i + 1})"
        created = _random_date(start, end)
        updated = _random_date(created, end)
        rows.append({
            "Summary": title[:255],
            "Description": desc,
            "Status": random.choice(STATUSES),
            "Priority": random.choice(PRIORITIES),
            "Labels": _pick_labels(),
            "Created": _fmt_dt(created),
            "Updated": _fmt_dt(updated),
        })
    return rows


def main() -> None:
    ap = argparse.ArgumentParser(description="Generate JIRA-importable CSV mock data (Product OS / Research Agent demo).")
    ap.add_argument("--output-dir", "-o", default=".", help="Directory for output CSVs")
    ap.add_argument("--per-type", "-n", type=int, default=50, help="Number of items per work type (Story, Task, Bug)")
    ap.add_argument("--seed", type=int, default=42, help="Random seed for reproducible output")
    args = ap.parse_args()

    random.seed(args.seed)
    start, end = _random_date_range(180)

    stories = generate_stories(args.per_type, start, end)
    tasks = generate_tasks(args.per_type, start, end)
    bugs = generate_bugs(args.per_type, start, end)

    fieldnames = ["Summary", "Description", "Status", "Priority", "Labels", "Created", "Updated"]
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    for name, rows in [("stories", stories), ("tasks", tasks), ("bugs", bugs)]:
        out_path = out_dir / f"jira_mock_{name}.csv"
        with open(out_path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames, quoting=csv.QUOTE_NONNUMERIC)
            w.writeheader()
            for row in rows:
                w.writerow({k: (v or "") for k, v in row.items()})
        print(f"Wrote {len(rows)} rows to {out_path}")

    print("Import in Jira: Create space → Import data → CSV. Import each file; set Work type to Story, Task, or Bug when mapping.")


if __name__ == "__main__":
    main()
