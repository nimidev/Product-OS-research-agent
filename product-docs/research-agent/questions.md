Ideal discovery questions (OpenAI PM demo)
Memory
What are users saying about ChatGPT Memory not working or forgetting things?
→ Feature requests (memory reliability), bugs (Memory not retaining), support (Memory not working — refund), PRD Memory (risks: reliability/forgetting), meeting notes (Memory reliability, “What I remember” page).
What did we ship for Memory and what’s the success criteria?
→ PRD: ChatGPT Memory (goal, solution, success metrics), roadmap (ChatGPT Memory), meeting notes (Sprint 42 Memory, blog post).
Where do we mention “What I remember” or memory controls?
→ Meeting notes (Sprint 42 — user-facing “What I remember” page), PRD Memory (view, edit, delete).
Search & organization
What’s the status of search and conversation organization?
→ Feature requests (conversation folders, search within conversations), bugs (search not finding old conversations), meeting notes (Search quality, 15% zero results, extend Search sprint), PRD: ChatGPT Search.
Why did we extend the Search sprint?
→ Meeting notes (Sprint 42 — Search ranking, 15% zero results, decision to extend).
What do users want for organizing or finding past conversations?
→ Feature requests (folders, tags, full-text search, conversation branching).
Enterprise & data privacy
What do enterprise customers need for data privacy and compliance?
→ Feature requests (enterprise data privacy, residency, SOC2, GDPR), support (data residency, BAA, audit logs), meeting notes (Acme Corp, data residency, SOC2, GDPR).
Are any deals blocked by data residency or compliance?
→ Support (Enterprise data residency requirement, blocking 500-seat deal), meeting notes (Acme Corp, data residency one-pager).
What’s on the roadmap for Enterprise and team?
→ Roadmap (ChatGPT Enterprise, Team plan, Connectors), PRD Team workspaces, meeting notes (Enterprise SSO, Team plan).
Voice
What’s the plan for Advanced Voice Mode and what issues are we seeing?
→ PRD: Advanced Voice Mode, roadmap (Advanced Voice Mode), feature requests (voice improvements), bugs (Voice mode disconnects), meeting notes (Voice latency).
What voice issues do users report?
→ Bugs (Voice mode disconnects mid-call), feature requests (latency, interruption, multilingual).
Custom GPTs & GPT Store
How are Custom GPTs doing and what’s going wrong?
→ PRD: Custom GPTs, roadmap (Custom GPTs, GPT Store), bugs (Custom GPTs fail to load), support (Custom GPT not loading), feature requests (discoverability, revenue share).
What do creators want for the GPT Store?
→ Feature requests (Custom GPT discoverability, categories, trending, search, revenue share).
API & developers
What are developers asking for on API rate limits and pricing?
→ Feature requests (API rate limits, pricing, committed tiers), bugs (rate limiting), support (API 429 blocking production).
What’s blocking production use of the API?
→ Support (API rate limit 429), feature requests (higher limits, predictable pricing).
Code interpreter & reliability
What problems do users have with code interpreter?
→ Feature requests (code execution, debugging, timeouts), bugs (code interpreter timeout, no partial output), meeting notes (code interpreter timeouts blocking).
What did user research say about power users and code?
→ Meeting notes (User research readout — code interpreter critical, timeouts blocking).
Mobile & platform
What mobile issues are we tracking?
→ Bugs (Mobile app crash on file upload, Android crash), support (Mobile app crash on Android), feature requests (mobile parity).
Content policy & safety
Where do we mention content policy or false positives?
→ Feature requests (image generation, content policy), bugs (DALL-E false positive content policy), support (Content policy appeal — false positive).
What do users say about DALL-E or image generation quality?
→ Feature requests (DALL-E, style consistency, aspect ratio, content policy).
Roadmap & prioritization
What did we decide for Q1 on Voice vs Search?
→ Meeting notes (Q1 prioritization — 70% Voice, 30% Search).
What’s shipped vs planned for 2024–2025?
→ Roadmap (GPT-4o, o1, Memory, Custom GPTs, Enterprise, Canvas, Projects, Team, Advanced Voice, Search, Sora, o3, Connectors, etc.).
What’s the rationale for prioritizing conversation organization?
→ Meeting notes (User research — conversation organization #1 pain), feature requests (folders, search).
Cross-cutting (good for synthesis demos)
Summarize everything we know about Memory: requests, bugs, PRD, and support.
→ Feature requests, bugs, PRD Memory, support tickets, meeting notes (single synthesis answer).
What’s blocking enterprise adoption and what are we doing about it?
→ Support (data residency, audit logs), feature requests (enterprise privacy, team workspaces), meeting notes (Acme Corp, security review), roadmap (Enterprise, Connectors).
What did the Acme Corp customer call tell us?
→ Meeting notes (Enterprise customer call — Acme Corp: data residency, SSO, audit logs, SOC2, GDPR).
What action items came out of Sprint 42?
→ Meeting notes (Ship Memory blog post, Continue Search ranking work).
Short / single-artifact (good for “search works” demos)
BAA or data residency documentation
Code interpreter timeout
Conversation branching
Team plan or Team workspaces
Deep Research
Sora video
o1 or o3 reasoning
Usage:
1–27: Full discovery; expect mixed types and synthesis.
28–34: Short queries; good for showing recall and citation.
For the research agent, store these in something like data/fixtures/demo_questions.json or a section in the PRD/README and run queries from that list during the demo.
