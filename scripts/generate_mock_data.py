#!/usr/bin/env python3
"""
Generate mock organizational data for the OpenAI ChatGPT product team demo.
Output: data/fixtures/*.json (6 files, ~380 items total).
Run: python scripts/generate_mock_data.py
"""

from __future__ import annotations

import json
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Deterministic for reproducible fixtures
random.seed(42)

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "data" / "fixtures"
BASE_DATE = datetime(2024, 1, 15, tzinfo=timezone.utc)


def _date_offset(days_min: int, days_max: int) -> datetime:
    days = random.randint(days_min, days_max)
    return BASE_DATE + timedelta(days=days)


def _iso(dt: datetime) -> str:
    return dt.isoformat()


# ---------------------------------------------------------------------------
# Feature requests (~100) — real topics from r/ChatGPT, forums, Twitter
# ---------------------------------------------------------------------------

FEATURE_REQUEST_SEEDS = [
    ("Custom instructions per conversation", "Users want to set different custom instructions for different conversation threads. Currently custom instructions apply globally which limits use cases for power users who discuss both work and personal topics.", ["customization", "ux"], "high", "consumer"),
    ("Conversation folders and organization", "Ability to organize conversations into folders or tags. With hundreds of conversations it becomes impossible to find past discussions. This is one of the most upvoted requests on the forum.", ["organization", "search"], "high", "consumer"),
    ("Search within my conversations", "Full-text search across all my past conversations. Critical for researchers and professionals who need to retrieve specific answers or code snippets from history.", ["search", "organization"], "high", "consumer"),
    ("Export conversations to Markdown/PDF", "Better export options including Markdown with code blocks preserved, and PDF for sharing. Current export is limited and loses formatting.", ["export", "sharing"], "medium", "consumer"),
    ("Longer context window handling", "Clear indication when context is being truncated and ability to summarize older parts to retain key facts. Users lose context in long debugging sessions.", ["context", "memory"], "high", "developer"),
    ("Better code execution and debugging", "Improve code interpreter: support for pip install, longer runtimes, better error messages, ability to re-run only failed cells. Heavily requested by dev users.", ["code", "developer"], "high", "developer"),
    ("Enterprise data privacy and residency", "Enterprise customers need guarantees that data stays in their region and is not used for model training. SOC2 and GDPR compliance documentation. Many enterprises are blocking ChatGPT until this is clear.", ["enterprise", "privacy", "compliance"], "critical", "enterprise"),
    ("Team workspaces and shared conversations", "Teams want a shared workspace where they can collaborate on conversations, share custom GPTs internally, and have centralized billing. Competitors already offer this.", ["team", "collaboration", "enterprise"], "high", "enterprise"),
    ("Memory that actually persists", "ChatGPT Memory frequently forgets or contradicts what was stored. Users need reliable memory with ability to view and edit stored facts. Major pain point in feedback.", ["memory", "reliability"], "critical", "consumer"),
    ("Voice mode improvements", "Lower latency, better interruption handling, support for multiple languages in same session. Voice is a differentiator but still has quality issues.", ["voice", "multimodal"], "medium", "consumer"),
    ("Custom GPT discoverability", "GPT Store is hard to discover and search. Creators want categories, trending, and better search. Revenue share concerns for top creators.", ["custom-gpt", "store"], "medium", "consumer"),
    ("API rate limits and pricing", "Developers need higher rate limits for production use and more predictable pricing. Pay-per-token with committed tiers would help. Current limits block serious applications.", ["api", "developer", "pricing"], "high", "developer"),
    ("Conversation branching", "Ability to branch from any message and try alternative responses. Essential for exploring different solutions without losing the main thread. Notion AI has this.", ["conversation", "ux"], "medium", "consumer"),
    ("Mobile app parity", "Mobile app lacks features from web: code interpreter, file uploads in some flows, plugins. Offline draft support requested.", ["mobile", "parity"], "medium", "consumer"),
    ("Image generation quality and control", "DALL-E in ChatGPT needs style consistency across images, better prompt following, and aspect ratio controls. Content policy too strict for legitimate use cases.", ["image", "multimodal", "content-policy"], "medium", "consumer"),
    ("Scheduled and recurring tasks", "Ability to schedule a task (e.g. daily digest) or have ChatGPT remind and run something on a schedule. Power user feature.", ["productivity", "scheduling"], "low", "consumer"),
    ("Better error messages", "When something fails (upload, code run, API), error messages are vague. Users need actionable errors and retry guidance.", ["reliability", "developer"], "medium", "developer"),
    ("Collaborative editing on Canvas", "Multiple users editing the same Canvas document in real time. Critical for team use of Canvas.", ["canvas", "collaboration", "team"], "high", "enterprise"),
    ("Plugins and tools reliability", "Plugins often fail or timeout. Need better observability for developers and fallback behavior when a plugin is down.", ["plugins", "reliability"], "medium", "developer"),
    ("Accessibility improvements", "Screen reader support, keyboard navigation, reduced motion option. Required for enterprise and education adoption.", ["accessibility", "compliance"], "high", "enterprise"),
]

def generate_feature_requests() -> list[dict]:
    items = []
    for i, (title, body, tags, priority, segment) in enumerate(FEATURE_REQUEST_SEEDS):
        for variant in range(5):  # 20 * 5 = 100
            idx = i * 5 + variant
            created = _date_offset(30 * idx, 30 * idx + 60)
            updated = created + timedelta(days=random.randint(0, 30))
            items.append({
                "id": f"mock:feature_request:{idx:03d}",
                "source": "mock",
                "type": "feature_request",
                "title": title if variant == 0 else f"{title} (variant {variant})",
                "body": body,
                "metadata": {"tags": tags, "votes": random.randint(5, 500), "customer_segment": segment, "priority": priority, "url": f"https://community.openai.com/t/{idx}"},
                "created_at": _iso(created),
                "updated_at": _iso(updated),
                "is_deleted": False,
            })
    return items[:100]  # cap at 100


# ---------------------------------------------------------------------------
# Bugs (~80) — known ChatGPT issues
# ---------------------------------------------------------------------------

BUG_SEEDS = [
    ("Memory not retaining information", "ChatGPT Memory fails to recall facts that were explicitly saved. Users report having to re-teach the same information. Affects both plus and free users. Engineering investigating embedding and retrieval path.", "high", "memory"),
    ("Code interpreter timeout with no output", "Long-running code interpreter jobs timeout and return no partial output. Users lose work. Need checkpointing or streaming of stdout.", "high", "code_interpreter"),
    ("GPT-4 'lazy' responses and refusal", "Model sometimes refuses to do simple tasks or gives truncated code. Temperature and system prompt tuning ongoing. Correlates with peak load.", "medium", "model"),
    ("Conversation history disappearing", "Users report conversations or entire history vanishing. May be related to account sync or mobile vs web. Support tickets spiking.", "critical", "storage"),
    ("Rate limiting too aggressive", "Legitimate heavy users hit rate limits during normal use. Enterprise and Team need higher limits. Documented limits don't match actual behavior.", "high", "api"),
    ("Custom GPTs fail to load", "Custom GPTs sometimes show loading error or stale version. Cache invalidation and CDN issues suspected. Affects GPT Store credibility.", "high", "custom_gpt"),
    ("Voice mode disconnects mid-call", "Advanced Voice Mode drops connection after 10-15 minutes. Mobile and desktop. Network stack under review.", "medium", "voice"),
    ("Mobile app crash on file upload", "iOS app crashes when uploading certain file types or large files. Reproduced in 3.2.1. Fix in progress.", "high", "mobile"),
    ("Image generation false positive content policy", "DALL-E rejects safe prompts (e.g. medical diagrams, historical figures). Users frustrated. Policy model being retuned.", "medium", "content_policy"),
    ("Search not finding old conversations", "In-app search misses clearly relevant past conversations. Embedding index and ranking need improvement. Top support complaint.", "high", "search"),
    ("Context window forgotten mid-conversation", "In long conversations model loses track of earlier context. No clear truncation warning. Affects complex debugging and writing tasks.", "high", "context"),
    ("Code block formatting broken", "Pasted code loses indentation or markdown code fences. Especially in shared links. Rendering bug in web and mobile.", "medium", "ux"),
    ("File upload fails silently", "Some PDFs and images fail to upload with no error message. Size and type limits not clearly communicated. Affects Canvas and analysis flows.", "medium", "upload"),
    ("Shared links expire unexpectedly", "Users report shared conversation links returning 404 before stated expiry. CDN and permission logic bug.", "low", "sharing"),
    ("Response truncation with no continuation", "Long responses get cut off with no 'continue' option. Confuses users. Related to token limits and streaming.", "medium", "model"),
    ("Slow response times during peak", "Latency spikes to 30+ seconds during US evening peak. Load balancing and capacity being addressed. Status page updated.", "high", "infrastructure"),
    ("Login loop on Safari", "Some Safari users get redirected to login repeatedly. Cookie/same-site issue. Reproduced in 17.2. Fix in next release.", "medium", "auth"),
]

def generate_bugs() -> list[dict]:
    items = []
    for i, (title, body, severity, component) in enumerate(BUG_SEEDS):
        for v in range(5):
            idx = i * 5 + v
            if idx >= 80:
                break
            created = _date_offset(20 * idx, 20 * idx + 45)
            items.append({
                "id": f"mock:bug:{idx:03d}",
                "source": "mock",
                "type": "bug",
                "title": title,
                "body": body,
                "metadata": {"severity": severity, "affected_users": random.randint(100, 50000), "component": component, "status": random.choice(["open", "open", "investigating", "resolved"]), "url": f"https://openai.com/issue/{idx}"},
                "created_at": _iso(created),
                "updated_at": _iso(created + timedelta(days=random.randint(1, 20))),
                "is_deleted": False,
            })
    return items[:80]


# ---------------------------------------------------------------------------
# Roadmap items (~40) — public OpenAI announcements
# ---------------------------------------------------------------------------

ROADMAP_SEEDS = [
    ("GPT-4o launch", "Multimodal model with vision and voice. Faster and cheaper. May 2024.", "2024-Q2", "shipped", "core"),
    ("o1 and o1 mini", "Reasoning models for complex problem-solving. Rolled out Sep 2024.", "2024-Q3", "shipped", "research"),
    ("ChatGPT Memory", "Model can remember facts across conversations. Launched April 2024. Iterating on reliability.", "2024-Q2", "shipped", "product"),
    ("Custom GPTs and GPT Store", "Users can create and share custom GPTs. Store launched Jan 2024.", "2024-Q1", "shipped", "product"),
    ("ChatGPT Enterprise", "Dedicated instance, SSO, admin controls, data residency. Launched Aug 2024.", "2024-Q3", "shipped", "enterprise"),
    ("Canvas", "Native document editing and generation in ChatGPT. Launched 2024.", "2024-Q2", "shipped", "product"),
    ("Projects", "Persistent project context and files. Replaces ad-hoc file uploads for power users.", "2024-Q4", "shipped", "product"),
    ("Advanced Voice Mode", "Real-time voice with low latency and interruption. Rolling out 2025.", "2025-Q1", "in_progress", "multimodal"),
    ("ChatGPT Search", "Web search and citation from within ChatGPT. Competing with Perplexity.", "2025-Q1", "in_progress", "product"),
    ("Sora video model", "Text-to-video generation. Limited release. Safety and quality bar for public.", "2025", "planned", "research"),
    ("Team plan", "Small team subscription with shared workspace and billing. Between Plus and Enterprise.", "2024-Q4", "shipped", "product"),
    ("Scheduled tasks", "Run a task on a schedule (e.g. daily digest). In backlog.", "2025", "planned", "product"),
    ("o3 and reasoning scale", "Next-gen reasoning model. Announced for 2025.", "2025", "planned", "research"),
    ("Deep Research", "Multi-step research with sources. Launched 2024. Improving citation quality.", "2024-Q3", "shipped", "product"),
    ("Connectors (Notion, Google, etc.)", "Enterprise connectors for knowledge base. In pilot.", "2025-Q2", "in_progress", "enterprise"),
    ("Operator / agentic workflows", "ChatGPT can take multi-step actions. Early access.", "2025", "in_progress", "research"),
]

def generate_roadmap() -> list[dict]:
    items = []
    for i, (title, body, quarter, status, team) in enumerate(ROADMAP_SEEDS):
        for v in range(3):
            idx = i * 3 + v
            if idx >= 40:
                break
            created = _date_offset(30 * idx, 30 * idx + 30)
            items.append({
                "id": f"mock:roadmap_item:{idx:03d}",
                "source": "mock",
                "type": "roadmap_item",
                "title": title,
                "body": body,
                "metadata": {"quarter": quarter, "status": status, "team": team},
                "created_at": _iso(created),
                "updated_at": _iso(created + timedelta(days=7)),
                "is_deleted": False,
            })
    return items[:40]


# ---------------------------------------------------------------------------
# Meeting notes (~80) — fabricated but realistic
# ---------------------------------------------------------------------------

MEETING_SEEDS = [
    ("Sprint 42 Review — Memory & Search", "Sprint 42 focused on Memory reliability and Search quality. Memory: fixed 3 bugs in retrieval, added user-facing 'What I remember' page. Search: improved ranking for code snippets, still seeing 15% of queries with zero results. Decision: extend Search sprint by 1 sprint. Action: Sarah to draft blog post on Memory improvements. Next sprint: Voice latency and Enterprise SSO.", "sprint_review", ["Sarah", "Mike", "Jen", "David"], ["Ship Memory blog post", "Continue Search ranking work"], ["Extend Search sprint"]),
    ("Enterprise customer call — Acme Corp", "Acme Corp (Fortune 500) evaluating ChatGPT Enterprise. Key concerns: data residency in EU, SSO with Okta, audit logs for compliance. They need SOC2 Type II and GDPR documentation. Competitor (Microsoft Copilot) already in their stack. We demonstrated Projects and Team plan. Action: Send data residency one-pager and schedule security review. Follow-up in 2 weeks.", "customer_call", ["Alex", "Jordan", "Acme CTO", "Acme Security"], ["Send data residency doc", "Schedule security review"], ["Prioritize EU region for Enterprise"]),
    ("Q1 prioritization — Voice vs Search", "Discussion on Q1 capacity: Engineering can fully staff either Advanced Voice Mode or ChatGPT Search, not both at same pace. Product presented user demand: Voice has higher NPS impact, Search has more competitive pressure (Perplexity). Decision: 70% Voice, 30% Search for Q1. Revisit when Voice ships. Enterprise data privacy came up again — Legal to confirm training opt-out language.", "prioritization", ["CPO", "VP Eng", "PM Voice", "PM Search"], ["Legal review opt-out language"], ["70/30 Voice vs Search"]),
    ("Incident post-mortem: Outage Jan 12", "30-min partial outage. Root cause: bad deploy to conversation service, rollback took 15 min. Impact: ~5% of requests failed, no data loss. Actions: add canary deployment, improve rollback automation. No customer data affected. Comms sent within 20 min.", "post_mortem", ["Incident lead", "SRE", "Comms"], ["Canary deployment", "Rollback runbook"], ["None"]),
    ("User research readout: Power users", "12 interviews with heavy users (5+ hrs/week). Themes: (1) Conversation organization is #1 pain — folders and search. (2) Memory is loved when it works, frustrating when it forgets. (3) Code interpreter is critical for devs; timeouts are blocking. (4) Team/workspace requested by 8/12. Recommend: prioritize search and memory reliability.", "user_research", ["Research", "PM", "Design"], ["Share full report", "Update roadmap inputs"], ["Align roadmap with research"]),
]

def generate_meeting_notes() -> list[dict]:
    items = []
    for i, (title, body, mtype, attendees, actions, decisions) in enumerate(MEETING_SEEDS):
        for v in range(16):
            idx = i * 16 + v
            if idx >= 80:
                break
            created = _date_offset(10 * idx, 10 * idx + 14)
            items.append({
                "id": f"mock:meeting_note:{idx:03d}",
                "source": "mock",
                "type": "meeting_note",
                "title": title if v == 0 else f"{title} — session {v}",
                "body": body,
                "metadata": {"meeting_type": mtype, "attendees": attendees, "action_items": actions, "decisions": decisions},
                "created_at": _iso(created),
                "updated_at": _iso(created),
                "is_deleted": False,
            })
    return items[:80]


# ---------------------------------------------------------------------------
# PRDs (~30) — fabricated from real shipped features
# ---------------------------------------------------------------------------

PRD_SEEDS = [
    ("PRD: ChatGPT Memory", "Goal: Enable ChatGPT to remember key facts about the user across conversations to reduce repetition and personalize experience. Problem: Users re-teach context every conversation. Solution: Optional memory layer with user control (view, edit, delete). Success: 30% of Plus users enable memory within 3 months; NPS +5 for memory users. Risks: Privacy perception; reliability (forgetting).", "Shipped", "Product", ["Legal", "Trust"]),
    ("PRD: Custom GPTs", "Goal: Let users create and share custom GPTs with instructions, knowledge, and tools. Problem: Users want tailored assistants without coding. Solution: No-code builder, GPT Store, revenue share for creators. Success: 1M+ public GPTs in 6 months; creator satisfaction. Risks: Quality and safety of public GPTs; discoverability.", "Shipped", "Product", ["Policy", "Platform"]),
    ("PRD: Team workspaces", "Goal: Shared workspace for teams with shared conversations, custom GPTs, and billing. Problem: Teams use individual accounts; no collaboration. Solution: Team plan with admin, shared context, and SSO option. Success: 10K teams in first quarter. Enterprise data privacy requirements apply.", "Shipped", "Enterprise", ["Security", "Sales"]),
    ("PRD: ChatGPT Search", "Goal: Answer questions with web search and citations. Problem: Users leave for Perplexity for real-time info. Solution: Integrated search with source links and optional search-only mode. Success: Reduce churn to search competitors; citation accuracy >90%.", "In progress", "Product", ["Search team"]),
    ("PRD: Advanced Voice Mode", "Goal: Real-time, low-latency voice with natural turn-taking. Problem: Current voice feels slow and robotic. Solution: New voice stack, interruption handling, emotion. Success: Voice NPS >50; usage 2x.", "In progress", "Multimodal", ["Research"]),
    ("PRD: Conversation branching", "Goal: Branch from any message to try alternative responses. Problem: Users want to explore without losing thread. Solution: Branch UI, merge not in scope for v1. Success: Adoption by 20% of power users.", "Backlog", "Product", ["Design"]),
]

def generate_prds() -> list[dict]:
    items = []
    for i, (title, body, status, team, stakeholders) in enumerate(PRD_SEEDS):
        for v in range(5):
            idx = i * 5 + v
            if idx >= 30:
                break
            created = _date_offset(40 * idx, 40 * idx + 30)
            items.append({
                "id": f"mock:prd:{idx:03d}",
                "source": "mock",
                "type": "prd",
                "title": title,
                "body": body,
                "metadata": {"author": "Product", "status": status, "team": team, "stakeholders": stakeholders},
                "created_at": _iso(created),
                "updated_at": _iso(created + timedelta(days=14)),
                "is_deleted": False,
            })
    return items[:30]


# ---------------------------------------------------------------------------
# Support tickets (~50)
# ---------------------------------------------------------------------------

SUPPORT_SEEDS = [
    ("Enterprise data residency requirement", "Customer (Healthcare Co) needs guarantee that all data remains in US. Asking for BAA and data residency documentation. Blocking 500-seat deal.", "high", "Healthcare Co", "enterprise"),
    ("Memory not working — refund request", "Plus user reports Memory has never worked for them. Multiple conversations. Requesting refund for 3 months. Escalated to Engineering.", "medium", "User_xxx", "plus"),
    ("API rate limit 429 blocking production", "Developer on Team plan hitting 429 with 50 RPM. Documentation says 60 RPM. Need higher limit or committed tier for production app.", "high", "DevCorp", "team"),
    ("Custom GPT not loading for users", "Published GPT returns error for 30% of visitors. Creator losing revenue. Ticket linked to Bug #4521.", "high", "Creator_yyy", "plus"),
    ("Billing dispute — duplicate charges", "User charged twice for annual Plus. Billing system bug. Refund issued. Apology and 1 month credit.", "medium", "User_zzz", "plus"),
    ("Content policy appeal — false positive", "Academic user's prompt about historical figures blocked. Appeal submitted. Policy team to review. Common theme in tickets.", "low", "University", "team"),
    ("Mobile app crash on Android", "App crashes on Samsung S24 after latest update. Crash logs submitted. Engineering investigating.", "high", "User_aaa", "plus"),
    ("Request for audit logs", "Enterprise customer needs 90-day audit log export for compliance. Feature not yet available. Workaround: API audit. On roadmap.", "medium", "Finance Corp", "enterprise"),
]

def generate_support_tickets() -> list[dict]:
    items = []
    for i, (title, body, severity, customer, tier) in enumerate(SUPPORT_SEEDS):
        for v in range(7):
            idx = i * 7 + v
            if idx >= 50:
                break
            created = _date_offset(15 * idx, 15 * idx + 20)
            items.append({
                "id": f"mock:support_ticket:{idx:03d}",
                "source": "mock",
                "type": "support_ticket",
                "title": title,
                "body": body,
                "metadata": {"severity": severity, "customer": customer, "customer_tier": tier, "resolution_status": random.choice(["open", "pending", "resolved"])},
                "created_at": _iso(created),
                "updated_at": _iso(created + timedelta(days=random.randint(0, 5))),
                "is_deleted": False,
            })
    return items[:50]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    FIXTURES_DIR.mkdir(parents=True, exist_ok=True)

    generators = [
        ("feature_requests.json", generate_feature_requests),
        ("bugs.json", generate_bugs),
        ("roadmap_items.json", generate_roadmap),
        ("meeting_notes.json", generate_meeting_notes),
        ("prds.json", generate_prds),
        ("support_tickets.json", generate_support_tickets),
    ]

    total = 0
    for filename, gen in generators:
        items = gen()
        path = FIXTURES_DIR / filename
        with open(path, "w") as f:
            json.dump(items, f, indent=2)
        print(f"  {filename}: {len(items)} items")
        total += len(items)

    print(f"\nTotal: {total} items written to {FIXTURES_DIR}")


if __name__ == "__main__":
    main()
