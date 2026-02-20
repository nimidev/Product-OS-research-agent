"""Monday.com connector — fetches items via GraphQL API."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

import httpx

from research_agent.connectors.base import BaseConnector, NormalizedItem

logger = logging.getLogger(__name__)

MONDAY_API_URL = "https://api.monday.com/v2"
RATE_LIMIT_BACKOFF = [1, 2, 4, 8, 16]
PAGE_SIZE = 100


class MondayConnector(BaseConnector):
    def __init__(
        self,
        api_key: str,
        board_ids: list[int],
        column_mapping: dict[str, str] | None = None,
    ) -> None:
        self._api_key = api_key
        self._board_ids = board_ids
        self._column_mapping = column_mapping or {
            "title": "name",
            "body": "description",
            "priority": "priority",
        }
        self._client = httpx.AsyncClient(
            headers={
                "Authorization": self._api_key,
                "Content-Type": "application/json",
                "API-Version": "2024-10",
            },
            timeout=30.0,
        )

    @property
    def source_name(self) -> str:
        return "monday"

    async def list_updated_items(self, since: datetime | None = None) -> list[NormalizedItem]:
        all_items: list[NormalizedItem] = []
        for board_id in self._board_ids:
            items = await self._fetch_board_items(board_id, since)
            all_items.extend(items)
        return all_items

    async def _fetch_board_items(
        self, board_id: int, since: datetime | None = None
    ) -> list[NormalizedItem]:
        items: list[NormalizedItem] = []
        cursor: str | None = None
        page = 0

        while True:
            page += 1
            query = self._build_query(board_id, cursor)
            data = await self._execute_query(query)

            if not data:
                break

            board_data = data.get("data", {}).get("boards", [{}])[0]
            items_page = board_data.get("items_page", {})
            raw_items = items_page.get("items", [])

            for raw in raw_items:
                try:
                    normalized = self.normalize_item(raw)
                    if since and normalized.updated_at and normalized.updated_at < since:
                        continue
                    items.append(normalized)
                except Exception:
                    logger.exception(
                        "Failed to normalize Monday item",
                        extra={"item_id": raw.get("id"), "source": "monday"},
                    )

            cursor = items_page.get("cursor")
            if not cursor or len(raw_items) < PAGE_SIZE:
                break

            logger.info("Monday board %d: fetched page %d (%d items)", board_id, page, len(items))

        return items

    def _build_query(self, board_id: int, cursor: str | None = None) -> str:
        cursor_arg = f', cursor: "{cursor}"' if cursor else ""
        return f"""
        query {{
            boards(ids: [{board_id}]) {{
                items_page(limit: {PAGE_SIZE}{cursor_arg}) {{
                    cursor
                    items {{
                        id
                        name
                        updated_at
                        created_at
                        column_values {{
                            id
                            text
                            value
                        }}
                        group {{
                            title
                        }}
                    }}
                }}
            }}
        }}
        """

    async def _execute_query(self, query: str) -> dict[str, Any] | None:
        for attempt, backoff in enumerate(RATE_LIMIT_BACKOFF):
            try:
                response = await self._client.post(
                    MONDAY_API_URL, json={"query": query}
                )
                if response.status_code == 429:
                    logger.warning("Monday rate limit hit, backing off %ds", backoff)
                    await asyncio.sleep(backoff)
                    continue
                if response.status_code in (401, 403):
                    logger.error(
                        "Monday auth error (%d): check API key", response.status_code,
                        extra={"source": "monday", "error_type": "auth"},
                    )
                    return None
                response.raise_for_status()
                return response.json()
            except httpx.HTTPStatusError:
                logger.exception("Monday API error on attempt %d", attempt + 1)
                if attempt < len(RATE_LIMIT_BACKOFF) - 1:
                    await asyncio.sleep(backoff)

        logger.error("Monday API: all retry attempts exhausted")
        return None

    def normalize_item(self, raw: Any) -> NormalizedItem:
        columns = {col["id"]: col.get("text", "") for col in raw.get("column_values", [])}

        body_col = self._column_mapping.get("body", "description")
        body = columns.get(body_col, "")

        tags: list[str] = []
        group = raw.get("group", {})
        if group and group.get("title"):
            tags.append(group["title"])

        priority_col = self._column_mapping.get("priority", "priority")
        priority = columns.get(priority_col, "")

        metadata: dict[str, Any] = {
            "tags": tags,
            "url": f"https://monday.com/boards/{raw.get('board_id', '')}",
            "columns": columns,
        }
        if priority:
            metadata["priority"] = priority

        updated_at = None
        if raw.get("updated_at"):
            try:
                updated_at = datetime.fromisoformat(raw["updated_at"].replace("Z", "+00:00"))
            except (ValueError, TypeError):
                pass

        created_at = None
        if raw.get("created_at"):
            try:
                created_at = datetime.fromisoformat(raw["created_at"].replace("Z", "+00:00"))
            except (ValueError, TypeError):
                pass

        return NormalizedItem(
            id=f"monday:{raw['id']}",
            source="monday",
            type=self._infer_type(raw, columns),
            title=raw.get("name", "Untitled"),
            body=body,
            metadata=metadata,
            created_at=created_at or datetime.now(timezone.utc),
            updated_at=updated_at or datetime.now(timezone.utc),
        )

    def _infer_type(self, raw: Any, columns: dict[str, str]) -> str:
        group_title = (raw.get("group", {}) or {}).get("title", "").lower()
        if "bug" in group_title or "issue" in group_title:
            return "bug"
        if "feature" in group_title or "request" in group_title:
            return "feature_request"
        if "roadmap" in group_title:
            return "roadmap_item"
        return "feature_request"

    async def health_check(self) -> bool:
        try:
            result = await self._execute_query("query { me { id } }")
            return result is not None and "data" in result
        except Exception:
            return False

    async def close(self) -> None:
        await self._client.aclose()
