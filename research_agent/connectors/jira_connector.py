"""Jira Cloud connector — fetches issues via REST API v3, normalizes to Entity using field_mappings.

Supports:
- Jira Platform REST API v3 (issues, projects, issue types, fields)
- Jira Software (Agile) REST API (boards, backlogs, sprints)
- OAuth 2.0 (3LO) bearer token auth
- Incremental sync via JQL `updated` filter
- Schema discovery for mapping UI (projects, boards, issue types, fields)
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote

import httpx

from research_agent.connectors.base import BaseConnector, ConnectorError
from research_agent.storage.models import Entity, EntityField, EntityType, SourceSystem

logger = logging.getLogger(__name__)

RATE_LIMIT_BACKOFF = [1, 2, 4, 8, 16]
PAGE_SIZE = 50
MAX_RESULTS_WINDOW = 10_000


class JiraConnector(BaseConnector):
    """Connector for a single Jira project/scope + entity_type pair."""

    def __init__(
        self,
        access_token: str,
        cloud_id: str,
        project_key: str,
        issue_type_names: list[str],
        entity_type: str | EntityType,
        field_mappings: dict[str, str],
        *,
        board_id: int | None = None,
        sprint_id: int | None = None,
        backlog_only: bool = False,
    ) -> None:
        self._access_token = access_token
        self._cloud_id = cloud_id
        self._project_key = project_key
        self._issue_type_names = issue_type_names
        self._entity_type = (
            entity_type.value if isinstance(entity_type, EntityType) else entity_type
        )
        self._field_mappings = field_mappings or {"summary": "title"}
        self._board_id = board_id
        self._sprint_id = sprint_id
        self._backlog_only = backlog_only

        self._base_url = f"https://api.atlassian.com/ex/jira/{cloud_id}"
        self._agile_base = f"https://api.atlassian.com/ex/jira/{cloud_id}/rest/agile/1.0"
        self._client = httpx.AsyncClient(
            headers={
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            timeout=30.0,
        )

    @property
    def source_name(self) -> str:
        return "jira"

    @property
    def sync_state_key(self) -> str:
        parts = ["jira", self._cloud_id, self._project_key]
        if self._board_id:
            parts.append(f"board:{self._board_id}")
        parts.append(self._entity_type)
        return ":".join(parts)

    @property
    def entity_type(self) -> str:
        return self._entity_type

    # ------------------------------------------------------------------
    # BaseConnector interface
    # ------------------------------------------------------------------

    async def list_updated_items(self, since: datetime | None = None) -> list[Entity]:
        if self._sprint_id:
            return await self._fetch_sprint_issues(since)
        if self._backlog_only and self._board_id:
            return await self._fetch_backlog_issues(since)
        return await self._fetch_via_jql(since)

    def normalize_item(self, raw: Any) -> Entity:
        fields_data: dict[str, Any] = raw.get("fields", {})

        title = str(fields_data.get("summary", "") or "")
        entity_fields: list[EntityField] = []

        for jira_field_id, canonical_name in self._field_mappings.items():
            value = self._extract_field_value(fields_data, jira_field_id)
            if canonical_name == "title":
                title = value or title
            else:
                entity_fields.append(
                    EntityField(
                        field_name=canonical_name,
                        field_type="text",
                        field_value=str(value),
                    )
                )

        if not title:
            title = raw.get("key", "Untitled")

        if not any(f.field_name == "title" for f in entity_fields):
            entity_fields.insert(
                0, EntityField(field_name="title", field_type="text", field_value=title)
            )

        updated_at = self._parse_datetime(fields_data.get("updated"))
        created_at = self._parse_datetime(fields_data.get("created"))

        issue_key = raw.get("key", raw.get("id", ""))
        entity_id = f"jira:{issue_key}"

        return Entity(
            id=entity_id,
            entity_type=EntityType(self._entity_type),
            source_system=SourceSystem.JIRA,
            source_id=str(issue_key),
            title=title,
            fields=entity_fields,
            chunks=[],
            created_at=created_at or datetime.now(timezone.utc),
            updated_at=updated_at or datetime.now(timezone.utc),
            is_deleted=False,
        )

    async def health_check(self) -> bool:
        # Use accessible-resources: same endpoint as OAuth callback; validates token and cloud_id.
        # No read:me or Jira REST needed; works even when /myself returns 404.
        try:
            resp = await self._client.get(
                "https://api.atlassian.com/oauth/token/accessible-resources",
                headers={"Accept": "application/json"},
            )
            if resp.status_code != 200:
                return False
            resources = resp.json()
            if not isinstance(resources, list) or len(resources) == 0:
                return False
            if not self._cloud_id:
                return True
            return any(r.get("id") == self._cloud_id for r in resources)
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Schema discovery (used by API endpoints for mapping UI)
    # ------------------------------------------------------------------

    async def fetch_accessible_resources(self) -> list[dict[str, Any]]:
        """List Atlassian Cloud sites accessible with current token."""
        try:
            resp = await self._client.get(
                "https://api.atlassian.com/oauth/token/accessible-resources"
            )
            resp.raise_for_status()
            return resp.json()
        except Exception:
            logger.exception("Failed to fetch accessible resources")
            return []

    async def fetch_projects(self) -> list[dict[str, Any]]:
        data = await self._request("GET", "/rest/api/3/project/search?maxResults=100")
        return data.get("values", []) if data else []

    async def fetch_boards(self, project_key: str | None = None) -> list[dict[str, Any]]:
        url = "/rest/agile/1.0/board?maxResults=100"
        if project_key:
            url += f"&projectKeyOrId={quote(project_key)}"
        data = await self._request_agile("GET", url)
        return data.get("values", []) if data else []

    async def fetch_issue_types(self, project_key: str) -> list[dict[str, Any]]:
        data = await self._request(
            "GET", f"/rest/api/3/project/{quote(project_key)}/statuses"
        )
        if not data:
            return []
        seen: dict[str, dict[str, Any]] = {}
        for item in data:
            name = item.get("name", "")
            if name and name not in seen:
                seen[name] = {"id": item.get("id"), "name": name}
        return list(seen.values())

    async def fetch_fields(self) -> list[dict[str, Any]]:
        """Fetch all fields (standard + custom) for this Jira instance."""
        data = await self._request("GET", "/rest/api/3/field")
        if not data or not isinstance(data, list):
            return []
        return [
            {
                "id": f.get("id", ""),
                "name": f.get("name", ""),
                "custom": f.get("custom", False),
                "schema": f.get("schema", {}),
            }
            for f in data
        ]

    async def fetch_sprints(self, board_id: int) -> list[dict[str, Any]]:
        data = await self._request_agile(
            "GET", f"/rest/agile/1.0/board/{board_id}/sprint?maxResults=50"
        )
        return data.get("values", []) if data else []

    # ------------------------------------------------------------------
    # Issue fetching strategies
    # ------------------------------------------------------------------

    async def _fetch_via_jql(self, since: datetime | None = None) -> list[Entity]:
        jql_parts = [f"project = {self._project_key}"]
        if self._issue_type_names:
            types_str = ", ".join(f'"{t}"' for t in self._issue_type_names)
            jql_parts.append(f"issuetype in ({types_str})")
        if since:
            jql_parts.append(f'updated >= "{since.strftime("%Y-%m-%d %H:%M")}"')
        jql = " AND ".join(jql_parts) + " ORDER BY updated DESC"

        return await self._paginate_search(jql)

    async def _fetch_backlog_issues(self, since: datetime | None = None) -> list[Entity]:
        """Fetch issues from a board's backlog via Agile API."""
        entities: list[Entity] = []
        start_at = 0

        while start_at < MAX_RESULTS_WINDOW:
            url = (
                f"/rest/agile/1.0/board/{self._board_id}/backlog"
                f"?maxResults={PAGE_SIZE}&startAt={start_at}"
            )
            data = await self._request_agile("GET", url)
            if not data:
                break

            issues = data.get("issues", [])
            for raw in issues:
                try:
                    entity = self.normalize_item(raw)
                    if since and entity.updated_at and entity.updated_at < since:
                        continue
                    if self._matches_issue_types(raw):
                        entities.append(entity)
                except Exception:
                    logger.exception(
                        "Failed to normalize Jira backlog item",
                        extra={"item_id": raw.get("key"), "source": "jira"},
                    )

            if len(issues) < PAGE_SIZE:
                break
            start_at += PAGE_SIZE

        return entities

    async def _fetch_sprint_issues(self, since: datetime | None = None) -> list[Entity]:
        """Fetch issues from a specific sprint via Agile API."""
        entities: list[Entity] = []
        start_at = 0

        while start_at < MAX_RESULTS_WINDOW:
            url = (
                f"/rest/agile/1.0/sprint/{self._sprint_id}/issue"
                f"?maxResults={PAGE_SIZE}&startAt={start_at}"
            )
            data = await self._request_agile("GET", url)
            if not data:
                break

            issues = data.get("issues", [])
            for raw in issues:
                try:
                    entity = self.normalize_item(raw)
                    if since and entity.updated_at and entity.updated_at < since:
                        continue
                    if self._matches_issue_types(raw):
                        entities.append(entity)
                except Exception:
                    logger.exception(
                        "Failed to normalize Jira sprint item",
                        extra={"item_id": raw.get("key"), "source": "jira"},
                    )

            if len(issues) < PAGE_SIZE:
                break
            start_at += PAGE_SIZE

        return entities

    async def _paginate_search(self, jql: str) -> list[Entity]:
        entities: list[Entity] = []
        start_at = 0

        while start_at < MAX_RESULTS_WINDOW:
            data = await self._request(
                "GET",
                f"/rest/api/3/search/jql?jql={quote(jql)}"
                f"&maxResults={PAGE_SIZE}&startAt={start_at}"
                f"&fields=*all",
            )
            if not data:
                break

            issues = data.get("issues", [])
            for raw in issues:
                try:
                    entities.append(self.normalize_item(raw))
                except Exception:
                    logger.exception(
                        "Failed to normalize Jira issue",
                        extra={"item_id": raw.get("key"), "source": "jira"},
                    )

            total = data.get("total", 0)
            start_at += PAGE_SIZE
            if start_at >= total or len(issues) < PAGE_SIZE:
                break

            logger.info(
                "Jira %s: fetched %d/%d issues",
                self._project_key,
                start_at,
                total,
            )

        return entities

    # ------------------------------------------------------------------
    # HTTP helpers
    # ------------------------------------------------------------------

    async def _request(self, method: str, path: str) -> Any | None:
        url = f"{self._base_url}{path}"
        return await self._do_request(method, url)

    async def _request_agile(self, method: str, path: str) -> Any | None:
        if path.startswith("/rest/agile"):
            url = f"{self._base_url}{path}"
        else:
            url = f"{self._agile_base}{path}"
        return await self._do_request(method, url)

    async def _do_request(self, method: str, url: str) -> Any | None:
        for attempt, backoff in enumerate(RATE_LIMIT_BACKOFF):
            try:
                resp = await self._client.request(method, url)
                if resp.status_code == 429:
                    retry_after = int(resp.headers.get("Retry-After", backoff))
                    logger.warning("Jira rate limit hit, backing off %ds", retry_after)
                    await asyncio.sleep(retry_after)
                    continue
                if resp.status_code in (401, 403):
                    logger.error(
                        "Jira auth error (%d): check OAuth token",
                        resp.status_code,
                        extra={"source": "jira", "error_type": "auth"},
                    )
                    return None
                if resp.status_code == 410:
                    logger.error(
                        "Jira site unavailable (410 Gone): cloud/site may have moved or connection is stale",
                        extra={"source": "jira", "error_type": "gone"},
                    )
                    raise ConnectorError(
                        "Jira site unavailable (410). The connected site may have moved or the connection is stale. Use “Reconnect Jira” below to sign in again; if it still fails, try a different Jira Cloud site or Atlassian account."
                    )
                resp.raise_for_status()
                return resp.json()
            except ConnectorError:
                raise
            except httpx.HTTPStatusError:
                logger.exception("Jira API error on attempt %d", attempt + 1)
                if attempt < len(RATE_LIMIT_BACKOFF) - 1:
                    await asyncio.sleep(backoff)

        logger.error("Jira API: all retry attempts exhausted")
        return None

    # ------------------------------------------------------------------
    # Field extraction helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_field_value(fields_data: dict[str, Any], field_id: str) -> str:
        """Extract a human-readable string from a Jira field value.

        Jira fields can be strings, objects with 'name'/'value', arrays, or nested.
        """
        raw = fields_data.get(field_id)
        if raw is None:
            return ""
        if isinstance(raw, str):
            return raw
        if isinstance(raw, (int, float, bool)):
            return str(raw)
        if isinstance(raw, dict):
            # Status, priority, issuetype, resolution, user, etc.
            for key in ("name", "displayName", "value", "emailAddress"):
                if key in raw:
                    return str(raw[key])
            # ADF (Atlassian Document Format) description
            if raw.get("type") == "doc" and "content" in raw:
                return JiraConnector._extract_adf_text(raw)
            return str(raw)
        if isinstance(raw, list):
            parts = []
            for item in raw:
                if isinstance(item, str):
                    parts.append(item)
                elif isinstance(item, dict):
                    parts.append(
                        item.get("name", "")
                        or item.get("displayName", "")
                        or item.get("value", "")
                        or str(item)
                    )
            return ", ".join(filter(None, parts))
        return str(raw)

    @staticmethod
    def _extract_adf_text(doc: dict[str, Any]) -> str:
        """Recursively extract plain text from Atlassian Document Format."""
        parts: list[str] = []
        for node in doc.get("content", []):
            if node.get("type") == "text":
                parts.append(node.get("text", ""))
            elif "content" in node:
                parts.append(JiraConnector._extract_adf_text(node))
        return "\n".join(filter(None, parts))

    @staticmethod
    def _parse_datetime(value: Any) -> datetime | None:
        if not value or not isinstance(value, str):
            return None
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            return None

    def _matches_issue_types(self, raw: dict[str, Any]) -> bool:
        """Check if issue matches configured issue type filter (for Agile endpoints)."""
        if not self._issue_type_names:
            return True
        issue_type = raw.get("fields", {}).get("issuetype", {})
        name = issue_type.get("name", "")
        return name in self._issue_type_names

    async def close(self) -> None:
        await self._client.aclose()
