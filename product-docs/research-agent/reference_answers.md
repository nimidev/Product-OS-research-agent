# Reference (gold) answers — US-008

This file defines **optimal Q&A exemplars** for the Research Agent chat. Used for:
- **Model selection**: compare candidate models on quality, structure, latency.
- **Regression evals**: ensure prompts/models don’t regress on these exemplars.
- **Onboarding**: clear expectations for PMs and engineers on what “good” looks like.

Each entry includes: **question**, **expected structure** (simple vs deep), **key entities**, **acceptance notes**, and the **reference answer** (AC1–AC7).

Source question set: [questions.md](./questions.md). PRD: [US-008.md](./US-008.md).

---

## 1. Simple lookup — short, direct

**Question:** Why did we extend the Search sprint?

**Expected structure:** Simple. 1–3 sentences, no multi-section layout.

**Key entities:** Meeting notes (Sprint 42 — Search ranking, 15% zero results, decision to extend).

**Acceptance notes:** Scope (Sprint 42) and reason (zero-result rate, ranking) must be stated. No fluff.

**Reference answer:**

We extended the Search sprint because of Search quality issues: 15% of queries were returning zero results and ranking needed work. The decision is documented in Sprint 42 meeting notes (Search ranking, 15% zero results, decision to extend).

*Evidence: meeting notes (Sprint 42).*

---

## 2. Simple lookup — single-artifact recall

**Question:** Where do we mention "What I remember" or memory controls?

**Expected structure:** Simple. Short list or 2–3 sentences with clear sources.

**Key entities:** Meeting notes (Sprint 42 — "What I remember" page), PRD Memory (view, edit, delete).

**Acceptance notes:** Must name both meeting notes and PRD; no generic filler.

**Reference answer:**

"What I remember" and memory controls appear in: (1) **Meeting notes, Sprint 42** — user-facing "What I remember" page; (2) **PRD: ChatGPT Memory** — view, edit, delete controls. No other entities in scope for this question.

*Evidence: meeting notes (Sprint 42), PRD Memory.*

---

## 3. Diagnostic — what’s going wrong

**Question:** What are users saying about ChatGPT Memory not working or forgetting things?

**Expected structure:** Medium. TL;DR or bottom line + key themes; evidence by entity type. No full Recommendations section required unless data supports it.

**Key entities:** Feature requests (memory reliability), bugs (Memory not retaining), support (Memory not working — refund), PRD Memory (risks: reliability/forgetting), meeting notes (Memory reliability, "What I remember" page).

**Acceptance notes:** Cross-entity synthesis (requests + bugs + support + PRD). Problems highlighted clearly. Timeframe/scope stated if inferable.

**Reference answer:**

**Bottom line:** Users are reporting Memory not working or forgetting things across feature requests, bugs, and support; the PRD explicitly calls out reliability/forgetting as risks.

**Key themes:**
- **Feature requests:** Asks for better memory reliability.
- **Bugs:** Memory not retaining information.
- **Support:** At least one ticket (Memory not working — refund).
- **PRD:** Risks called out for reliability and forgetting.

**Evidence:** Feature requests (memory reliability), bugs (Memory not retaining), support (Memory not working — refund), PRD Memory (risks), meeting notes (Memory reliability). No timeframe specified in query; results reflect all available data.

**Gaps:** We don’t have volume (e.g. count of support tickets) in this summary; adding support ticket counts would strengthen the picture.

---

## 4. Strategy / synthesis — full structure

**Question:** Summarize everything we know about Memory: requests, bugs, PRD, and support.

**Expected structure:** Deep. TL;DR, Key Insights, Evidence / Data sources, optional Recommendations or Deep dives as needed.

**Key entities:** Feature requests, bugs, PRD Memory, support tickets, meeting notes.

**Acceptance notes:** Multiple entity types; facts vs interpretation clear; scope stated; no invented metrics.

**Reference answer:**

**TL;DR:** Memory has clear demand (feature requests, PRD) and defined success criteria, but reliability and forgetting are recurring issues in bugs and support. Meeting notes and PRD align on risks and the "What I remember" surface.

**Key insights**
- **Demand and scope:** Feature requests emphasize memory reliability; PRD defines goal, solution, and success metrics; roadmap and Sprint 42 meeting notes reference Memory ship and blog post.
- **Problems:** Bugs (Memory not retaining), support (e.g. Memory not working — refund), and PRD explicitly list reliability/forgetting as risks.
- **Cross-signal:** Same theme (reliability, forgetting) shows up in feature requests, bugs, support, and PRD — not isolated to one channel.

**Evidence**
- Feature requests: memory reliability.
- Bugs: Memory not retaining.
- Support: Memory not working (refund ticket).
- PRD: ChatGPT Memory (goal, solution, success metrics, risks).
- Meeting notes: Sprint 42 Memory, "What I remember" page.

**Recommendations**
- Track support ticket volume and bug recurrence for Memory reliability to prioritize fixes.
- Use the PRD success metrics to measure whether reliability improvements move the needle.

*Scope: all available entity types above; no timeframe filter applied.*

---

## 5. Short single-artifact (search recall)

**Question:** Code interpreter timeout

**Expected structure:** Simple. 1–3 sentences: what we have (artifacts) and one-line takeaway if obvious.

**Key entities:** Feature requests (code execution, debugging, timeouts), bugs (code interpreter timeout, no partial output), meeting notes (code interpreter timeouts blocking).

**Acceptance notes:** User asked for a single topic; answer should be a short, direct recall of relevant items, not a full research report.

**Reference answer:**

We have feature requests (code execution, debugging, timeouts), bugs (code interpreter timeout, no partial output), and meeting notes (code interpreter timeouts blocking). The main theme is **timeouts** — both as a bug and as a blocker called out in meeting notes.

*Evidence: feature requests, bugs, meeting notes.*

---

## 6. Diagnostic + strategy — enterprise blocking

**Question:** What’s blocking enterprise adoption and what are we doing about it?

**Expected structure:** Deep. TL;DR, Key insights, Evidence, Recommendations.

**Key entities:** Support (data residency, audit logs), feature requests (enterprise privacy, team workspaces), meeting notes (Acme Corp, security review), roadmap (Enterprise, Connectors).

**Acceptance notes:** Problems (blockers) must be prominent; roadmap/actions (what we’re doing) must be grounded in entities.

**Reference answer:**

**TL;DR:** Enterprise adoption is blocked mainly by data residency and compliance (support, Acme Corp); we’re addressing it via roadmap (Enterprise, Connectors) and security review, but support and feature requests show the ask is ongoing.

**Key insights**
- **Blockers:** Support highlights data residency and audit logs; Acme Corp meeting notes (security review) align on data residency, SSO, SOC2, GDPR.
- **Ask from customers:** Feature requests (enterprise privacy, team workspaces) and support (data residency, audit logs).
- **What we’re doing:** Roadmap includes Enterprise and Connectors; meeting notes reference Acme Corp security review and one-pager.

**Evidence**
- Support: data residency, audit logs.
- Feature requests: enterprise privacy, team workspaces.
- Meeting notes: Acme Corp, security review, data residency one-pager.
- Roadmap: Enterprise, Connectors.

**Recommendations**
- Tie Connectors and Enterprise roadmap items to specific data-residency and audit-log asks so we can close the loop with customers like Acme Corp.

*Scope: enterprise adoption; entities as above; no explicit timeframe.*

---

## Summary table

| # | Question type           | Structure | Entities (main)                          |
|---|-------------------------|-----------|------------------------------------------|
| 1 | Simple lookup           | Simple    | Meeting notes                            |
| 2 | Simple lookup           | Simple    | Meeting notes, PRD                       |
| 3 | Diagnostic              | Medium    | FR, bugs, support, PRD, meeting notes   |
| 4 | Strategy / synthesis    | Deep      | FR, bugs, PRD, support, meeting notes   |
| 5 | Short single-artifact   | Simple    | FR, bugs, meeting notes                 |
| 6 | Diagnostic + strategy   | Deep      | Support, FR, meeting notes, roadmap    |

These reference answers are the **gold set** for model selection and regression evals. When adding or changing questions, keep the same format (structure, entities, acceptance notes, reference answer) and align with AC1–AC7.
