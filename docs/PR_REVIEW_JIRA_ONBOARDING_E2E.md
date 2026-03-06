# E2E / PR Review: Jira Onboarding & Related Changes

Engineering manager review checklist for the Jira OAuth, onboarding wizard, search links, and field-mapping changes before PR.

---

## 1. Scope of Recent Changes

- **OAuth & redirect**: Return step + entity map in localStorage; OAuth callback adds `site_url` to fragment; frontend persists token/cloud_id/site_url after OAuth.
- **Sync 410**: Jira API uses `/rest/api/3/search/jql`; 410 repair updates cloud_id and retries.
- **Jira links in search**: `site_url` stored in integration config; `_enrich_raw_results` builds `https://{site_url}/browse/{issue_key}`; backfill from accessible-resources when `site_url` missing.
- **Connect Jira UX**: Simplified to OAuth-only; `GET /integrations/jira/oauth/ready`; optional Advanced (Client ID/Secret); no visible Cloud ID/Token fields.
- **Step 3 duplication fix**: Monday "Map your boards" only when `needsMonday && step === 3`.
- **Jira field selection**: Sorted by name, autocomplete (type-to-search), type in brackets instead of API id; "Not mapped" option.

---

## 2. Tests – Status & Gaps

| Area | Current coverage | Gaps / suggested |
|------|------------------|------------------|
| **API – Jira** | None | Add: GET/PUT `/integrations/jira` (with `site_url`), GET `/integrations/jira/oauth/ready` (ready vs not ready). |
| **API – OAuth callback** | None | Optional: mock token exchange + redirect fragment (code path); error redirect when code missing / token exchange fails. |
| **Storage** | Integration config not exercised with new fields | Add: `upsert_integration_config` / `get_integration_config` with `site_url` for jira. |
| **Memory** | No tests for `_enrich_raw_results` | Add: Jira result gets `url` when config has `site_url`; no url when `site_url` missing and backfill fails. |
| **Connectors** | Jira normalize, sync_state_key, health | OK. Optional: fetch_fields schema shape. |
| **Frontend** | No automated tests | Manual E2E: Connect Jira (env creds + Advanced), OAuth return, mapping step, search links. Consider Playwright/Cypress later. |

---

## 3. Edge Cases & Error Handling

| Scenario | Handled? | Notes |
|----------|----------|--------|
| OAuth callback with no `code` | Yes | Redirect to `#jira_oauth_error=missing_code`. |
| Token exchange 4xx/5xx | Yes | Redirect to frontend with message in fragment; frontend shows error. |
| No access_token in token response | Yes | Redirect `#jira_oauth_error=no_access_token`. |
| Credentials missing (authorize or callback) | Yes | ready returns `ready: false`; authorize/callback raise HTTPException or redirect. |
| accessible-resources empty on callback | Yes | `cloud_id` from first resource; `site_url` can be empty (backfill later). |
| All resources return 410 on probe | Yes | First resource used for cloud_id; sync may 410 and trigger repair. |
| Jira config without site_url (old config) | Yes | Backfill in `_enrich_raw_results`; persist after first success. |
| Backfill fails (network, 401) | Yes | Log warning; Jira results keep empty url. |
| Wizard: ready false + no Advanced creds | Yes | Button disabled; message shown. |
| Wizard: OAuth return in same tab (no opener) | Yes | sessionStorage + redirect to onboarding=1. |
| Reconnect Jira | Yes | Clears token/cloud_id/site_url; PUT sends empty; user goes to Connect step. |
| Step 3 Monday vs Jira | Yes | `needsMonday && step === 3` vs `needsJira && !needsMonday && step === 3`. |
| Jira field select: empty options | Yes | "No matching field" when filtered list empty. |
| Jira entity id without colon | Yes | `issue_key = eid.split(":", 1)[1] if ":" in eid else (entity.source_id if entity else "")`. |

---

## 4. Security & Data

- **Token in fragment**: Correct; not sent to server logs. Callback redirects with fragment.
- **site_url in fragment**: Same; client-only.
- **Backfill**: Uses stored api_key (token); one GET to Atlassian; no user input in URL.
- **PUT /integrations/jira**: Preserves existing client_secret when not sent; no accidental clear.

---

## 5. Documentation

- **JIRA_OAUTH_SETUP.md**: Update to mention `GET /integrations/jira/oauth/ready` and simplified wizard (env-only flow).
- **JIRA_OAUTH_ONBOARDING_REDIRECT_REPORT.md**: Update flow: optional PUT before authorize when using Advanced; OAuth return persists token/cloud_id/site_url via PUT from frontend.

---

## 6. Suggested Improvements (Pre-/Post-PR)

1. **Tests**: Add the tests listed in §2 (Jira API, storage site_url, memory Jira URL).
2. **Doc**: One-line in JIRA_OAUTH_SETUP.md for `oauth/ready` and "simplified Connect step when credentials are in env."
3. **Frontend error on PUT after OAuth**: `applyJiraOAuthFromStorage` fires PUT and ignores failures; consider showing a toast or inline error if PUT fails so user can retry or reconnect.
4. **Jira field select**: Keyboard nav (arrow down/up + Enter) in dropdown for accessibility (optional).
5. **E2E**: Manual test script or automated (Playwright) for: open wizard → Connect Jira (env) → OAuth → return → map project → map fields → sync → search → open Jira link.

---

## 7. Pre-PR Checklist

- [x] All new/updated tests pass (`pytest tests/`) — Jira API, storage site_url, memory Jira URL tests added.
- [ ] No linter errors on touched files.
- [ ] Jira Connect step: works with env-only; works with Advanced (Client ID/Secret); shows error when not ready.
- [ ] OAuth return: token/cloud_id/site_url saved; wizard step restored; Continue enabled.
- [ ] Search: Jira results show correct browse link (and backfill works when site_url was missing).
- [ ] Step 3: Only one of "Map your boards" or "Map your Jira projects" visible per flow.
- [ ] Jira field dropdown: sort, search, type in brackets, "Not mapped" clears.
- [ ] Reconnect Jira clears connection and returns to Connect step.
- [ ] Docs updated if needed.
