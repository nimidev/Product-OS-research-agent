# Jira OAuth Redirect → Onboarding Flow — Evaluation Report

## 1. Current flow summary

- **OAuth start**: User is in OnboardingWizard **step 2** (Connect Jira). Clicks “Connect with Jira (OAuth)”. Frontend saves config via `PUT /integrations/jira`, then opens **new tab**: `window.open(RESEARCH_API_URL + '/integrations/jira/oauth/authorize', '_blank')`.
- **Authorize**: Backend `GET /integrations/jira/oauth/authorize` redirects to Atlassian with `state=jira_os_research` and `redirect_uri` = backend callback (e.g. `http://localhost:8000/integrations/jira/oauth/callback`). No “return step” or frontend path is encoded in `state`.
- **Callback**: Jira redirects that **same tab** to backend callback with `?code=...&state=jira_os_research`. Backend exchanges code for token, fetches `cloud_id`, then redirects to **frontend** with hash: `{jira_oauth_frontend_origin}/#jira_oauth_connected&access_token=...&cloud_id=...` (e.g. `http://localhost:3000/#jira_oauth_connected&...`).
- **Frontend (App.tsx)**:
  - **Popup path** (`window.opener` exists): OAuth effect writes token to `localStorage.jira_oauth_result`, focuses opener, closes popup. **Opener** (wizard tab) gets `storage` event, writes token/cloud_id to sessionStorage, dispatches `jira_oauth_result`. Wizard (still at step 2) has listeners that call `applyJiraOAuthFromStorage()` so token/connection status update; user can click Continue → step 3 (mapping). This path can work.
  - **Same-tab path** (no `window.opener` — e.g. new tab lost opener, or user opened OAuth in same tab): OAuth effect writes token/cloud_id to sessionStorage, then `window.location.replace(pathname + '?onboarding=1')` → **full page reload**. App loads with `?onboarding=1`, sets `forceOnboardingViaUrlRef`, fetches Monday config, sets `showOnboarding = true`, mounts **OnboardingWizard with default state**: `step = 1`, fresh `entityToolMap`, etc. User lands on **Step 1** (entity → tool mapping), not step 2 or 3. Token is in sessionStorage and is applied when `applyJiraOAuthFromStorage` runs on mount, but the visible step is still 1, so the flow does **not** continue with the mapping process until the user clicks through 1 → 2 again.

**Mapping process** in the wizard: for Jira, step **3** = “Map your Jira projects” (project + issue types), steps **4..(4+N−1)** = field mapping per entity, then sync/complete. These are the steps that should follow “Connect Jira” (step 2).

---

## 2. Root cause

- **Step and context not restored after redirect.** When the return from Jira OAuth happens in the **same tab** (no opener), the app does a full reload with only `?onboarding=1`. The wizard always initializes with `useState(1)` and never reads a “resume step” from URL or storage, so the user is sent back to **step 1** instead of resuming at **step 2** (Connect Jira) or continuing to **step 3** (mapping).
- **No persisted “Jira OAuth return” state.** Nothing is stored before opening OAuth (e.g. “return to step 2” or “Jira flow”) and nothing is restored when the callback lands on the frontend, so the wizard cannot resume the Jira flow at the correct step.
- **Popup path fragility.** If the OAuth tab loses `window.opener` (browser behavior, new-tab-from-link, etc.), the same-tab path is used and the above applies. Relying only on the popup path is brittle.

---

## 3. Recommended changes

### 3.1 Persist “return step” before opening OAuth (frontend)

- **File**: `ui/src/OnboardingWizard.tsx`
- **Where**: In `handleConnectWithJiraOAuth`, immediately before `window.open(...)`:
  - Set `sessionStorage.setItem('jira_oauth_return_step', '2')` so that when the user returns (same-tab or after reload), the wizard can restore step 2.
  - Persist `entityToolMap` (e.g. `sessionStorage.setItem('jira_oauth_entity_tool_map', JSON.stringify(entityToolMap))`) so that after same-tab reload the wizard still shows “Jira” for the chosen entities and the Jira step 2/3 flow is visible (otherwise `needsJira` is false and step 2 would be the wrong screen).

### 3.2 Restore step when wizard mounts (frontend)

- **File**: `ui/src/OnboardingWizard.tsx`
- **Where**: (1) Initialize `entityToolMap` from a lazy initializer that reads `jira_oauth_entity_tool_map` from sessionStorage and merges with defaults (then remove the key). (2) On mount, in a `useEffect`, read `jira_oauth_return_step`; if present and valid, set step and remove the key. Run after `applyJiraOAuthFromStorage` so step 2 shows with token applied. After same-tab redirect the user lands on **step 2** with Jira entities and connection OK and can click Continue to **step 3** (mapping).

### 3.3 Same-tab redirect: keep onboarding=1 only (no change to backend redirect URL)

- Backend already redirects to `{frontend_origin}/#jira_oauth_connected&...`. No change needed there.
- **File**: `ui/src/App.tsx`
- **Where**: In the OAuth effect, in the “no opener” branch, keep `window.location.replace(base + separator + 'onboarding=1')` so the app reloads and shows the wizard. The fix is on the wizard side (restore step from `jira_oauth_return_step`), not the redirect URL.

### 3.4 Optional: encode return path in OAuth state (backend + frontend)

- **File**: `research_agent/api/server.py` — `jira_oauth_authorize`: optionally accept a query param (e.g. `return_step=2`) and pass it in `state` (e.g. `state=jira_os_research_step_2`). Callback then redirects to frontend with that in the hash (e.g. `#jira_oauth_connected&...&return_step=2`). Frontend OAuth effect and wizard can then use `return_step` from the hash/URL instead of sessionStorage. This is redundant if you implement 3.1+3.2; use it only if you want a single source of truth in the URL.

### 3.5 Concrete steps (minimal fix)

1. **OnboardingWizard.tsx**
   - In `handleConnectWithJiraOAuth`, before `window.open(...)`, add:
     - `sessionStorage.setItem('jira_oauth_return_step', '2');`
     - `sessionStorage.setItem('jira_oauth_entity_tool_map', JSON.stringify(entityToolMap));`
   - Initialize `entityToolMap` with a lazy initializer that restores from `jira_oauth_entity_tool_map` if present (then remove key).
   - Add a `useEffect` that runs once on mount: read `jira_oauth_return_step` from sessionStorage; if present, set step to that number (valid integer >= 1), then remove the key. Ensure this runs after `applyJiraOAuthFromStorage` so that when step 2 is restored, token/cloud_id are already in state.
2. **App.tsx**
   - No change required for the redirect URL; keep `?onboarding=1` for same-tab return.
3. **Backend**
   - No change required for callback or redirect URL.

Result: After Jira OAuth redirect (same-tab or popup), the user either stays on step 2 (popup) or returns to the wizard at **step 2** (same-tab) with token applied, and can continue to **step 3** (mapping) and beyond.
