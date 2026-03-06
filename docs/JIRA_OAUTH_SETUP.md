# Jira OAuth 2.0 (3LO) setup

Configure your Atlassian app, then connect Jira in the product — no server `.env` required. This follows [Atlassian’s OAuth 2.0 (3LO) for Jira Cloud](https://developer.atlassian.com/cloud/jira/platform/oauth-2-3lo-apps/).

---

## 1. Create or open your app

1. Go to [Atlassian Developer Console](https://developer.atlassian.com/console/myapps/).
2. Create a new app or select your existing one (e.g. **OS Research**).

---

## 2. Add APIs and scopes (required)

**You must add APIs before OAuth will work.** Otherwise you’ll see: *"Your app doesn't have any APIs. Add APIs to your app."*

1. In the left menu, select **Permissions**.
2. Under **APIs**, find **Jira platform REST API** (and optionally **Jira Software Cloud REST API** for boards/sprints).
3. Click **Add** next to **Jira platform REST API**.
4. In the list of scopes, add at least:
   - **Read: Jira work** (`read:jira-work`) — issues, projects, search.
   - **Read: Jira user** (`read:jira-user`) — user info.
5. Add **User Identity API** (click **Add**), then add **Read user's personal information** (`read:me`). This lets the connection test succeed when Jira’s `/myself` returns 404 on some sites.
6. (Optional) Add **Jira Software Cloud REST API** and any scopes you need for boards/backlog/sprints.
7. For refresh tokens (so you can get new access tokens without re-consent), the app will request the **Offline access** scope (`offline_access`). Ensure it’s available for the APIs you added (it’s usually under the same API or account scopes).
8. Save / **Add** as prompted.

Our app requests these scopes in the authorize URL:

- `read:jira-work`
- `read:jira-user`
- `read:me` (add User Identity API in Permissions)
- `offline_access`

They must be added to your app under **Permissions** or the consent screen will fail or show no access.

---

## 3. Set the OAuth callback URL

1. In the left menu, select **Authorization**.
2. Next to **OAuth 2.0 authorization code grants (3LO)**, click **Configure**.
3. Under **Callback URLs**, enter **exactly** (one per line if you have several):

   **Local development:**

   ```text
   http://localhost:8000/integrations/jira/oauth/callback
   ```

   **Production:**

   ```text
   https://your-api-host.example.com/integrations/jira/oauth/callback
   ```

   Use your real API base URL and path; the `redirect_uri` we send in the OAuth request must match one of these.
4. Click **Save changes**.

---

## 4. Connect Jira in the product (no .env)

In the onboarding wizard, on the **Connect Jira** step:

1. **Client ID** — In Atlassian Developer Console, open your app → **Settings**. Copy **Client ID** and paste it into the **Client ID** field.
2. **Client Secret** — On the same **Settings** page, click **Show** next to **Secret**, copy it, and paste into the **Client Secret** field.
3. Click **Connect with Jira (OAuth)**. Your credentials are saved and a new tab opens for Atlassian sign-in and consent.
4. After authorizing, return to the wizard. **Cloud ID** and **OAuth Access Token** are filled automatically.
5. Click **Test Connection**, then **Continue**.

**Cloud ID** is not in the Atlassian Settings page — you get it only from the OAuth flow (or from the `accessible-resources` API). The form fills it for you after you use **Connect with Jira (OAuth)**.

---

## 5. Optional: server environment variables

If you prefer to configure OAuth on the server instead of in the UI, set these in the Research Agent backend `.env`:

| Variable | Description |
|----------|-------------|
| `JIRA_OAUTH_CLIENT_ID` | **Client ID** from your app’s **Settings** |
| `JIRA_OAUTH_CLIENT_SECRET` | **Secret** from your app’s **Settings** |
| `JIRA_OAUTH_REDIRECT_URI` | (Optional) Must match a Callback URL in section 3. Default: `http://localhost:8000/integrations/jira/oauth/callback` |
| `JIRA_OAUTH_FRONTEND_ORIGIN` | (Optional) UI origin for post-login redirect. Default: `http://localhost:3000` |

Aliases (used only if the vars above are not set): `JIRA_CLIENT_ID`, `JIRA_SECRET`.

When both are set, the server uses stored credentials (from the UI) first, then falls back to these env vars. Restart the API after changing them.

**Wizard & readiness:**
- `GET /integrations/jira/oauth/ready` — Returns `{ "ready": true }` when Client ID/Secret are available (env or DB); otherwise `{ "ready": false, "message": "..." }`. The Connect Jira step uses this to show a single “Connect with Jira (OAuth)” button when credentials are in env.

**Debug endpoints:**
- `GET /integrations/jira/oauth/debug` — Runs a fake token exchange; use to verify credentials and redirect_uri. 400/`invalid_grant` = credentials OK.
- `POST /integrations/jira/oauth/debug-token` — Test with a real code. When the callback fails, copy the `code` from the URL (`?code=eyJ...`), then:
  ```bash
  curl -X POST http://localhost:8000/integrations/jira/oauth/debug-token \
    -H "Content-Type: application/json" \
    -d '{"code":"PASTE_THE_CODE_FROM_CALLBACK_URL"}'
  ```
  If this returns 200, the callback has a bug. If 401, the request format or Atlassian config is the issue.

---

## 6. Getting an access token (without the wizard)

- **In-app (recommended):** Use the **Connect Jira** step as in section 4.
- **Direct URL:** Open in the browser:  
  `http://localhost:8000/integrations/jira/oauth/authorize`  
  Credentials must already be saved (via the wizard or env). After consent, you’re redirected to the UI with `access_token` and `cloud_id` in the URL fragment.

---

## Troubleshooting

| Message | What to do |
|--------|------------|
| *"Your app doesn't have any APIs"* | Add at least **Jira platform REST API** under **Permissions**, then add the scopes above. |
| *"redirect_uri mismatch"* | Ensure **Callback URLs** in **Authorization** exactly match `JIRA_OAUTH_REDIRECT_URI` (including scheme, host, port, path). |
| Consent screen shows no access / wrong scopes | In **Permissions**, add the requested scopes (`read:jira-work`, `read:jira-user`, `offline_access`) to the APIs you added. |
| Token exchange fails / *"Unauthorized"* | **Client ID & Secret:** Re-copy from Atlassian app **Settings** (no extra spaces). **Callback URL:** In **Authorization** → Callback URLs, the value must match *exactly* what the server uses (e.g. `http://localhost:8000/integrations/jira/oauth/callback`). Same scheme, host, port, path — no trailing slash. Try creating a **new OAuth app** in the developer console and use its Client ID/Secret to rule out config corruption. Use `POST /integrations/jira/oauth/debug-token` with a fresh code (from Network tab) to test the exchange directly. |
| *"authorization_code has mismatched aud"* | The code was issued for a different Client ID than the one used for the token exchange. The callback now always uses the same credentials as the authorize flow (DB or env). Ensure the wizard and env are not configured with different app credentials. |
| *"Jira OAuth is not configured"* | Enter Client ID and Client Secret in the Connect Jira step (from Atlassian app **Settings**), then click **Connect with Jira (OAuth)**. No .env needed. |

For full 3LO details (authorize URL, token exchange, `audience`, `state`), see [Implementing OAuth 2.0 (3LO)](https://developer.atlassian.com/cloud/jira/platform/oauth-2-3lo-apps/#implementing-oauth-2-0-3lo) in the Atlassian docs.
