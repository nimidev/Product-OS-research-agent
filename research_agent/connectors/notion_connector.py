"""Notion connector — fetches pages from configured databases, normalizes to Entity using field_mappings."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

import httpx

from research_agent.connectors.base import BaseConnector
from research_agent.storage.models import Entity, EntityField, EntityType, SourceSystem

logger = logging.getLogger(__name__)

NOTION_API_URL = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"
RATE_LIMIT_BACKOFF = [1, 2, 4, 8, 16]
PAGE_SIZE = 100


class NotionConnector(BaseConnector):
    def __init__(
        self,
        api_key: str,
        database_id: str,
        entity_type: str | EntityType,
        field_mappings: dict[str, str],
    ) -> None:
        self._api_key = api_key
        self._database_id = database_id.strip()
        self._entity_type = (
            entity_type.value if isinstance(entity_type, EntityType) else entity_type
        )
        self._field_mappings = field_mappings or {"Title": "title", "content": "transcript"}
        self._client = httpx.AsyncClient(
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Notion-Version": NOTION_VERSION,
                "Content-Type": "application/json",
            },
            timeout=30.0,
        )

    @property
    def source_name(self) -> str:
        return "notion"

    @property
    def entity_type(self) -> str:
        return self._entity_type

    async def list_updated_items(self, since: datetime | None = None) -> list[Entity]:
        return await self._fetch_database_pages(since)

    async def _fetch_database_pages(
        self, since: datetime | None = None
    ) -> list[Entity]:
        entities: list[Entity] = []
        has_more = True
        start_cursor: str | None = None

        body: dict[str, Any] = {"page_size": PAGE_SIZE}
        if since:
            body["filter"] = {
                "timestamp": "last_edited_time",
                "last_edited_time": {"after": since.isoformat()},
            }

        while has_more:
            if start_cursor:
                body["start_cursor"] = start_cursor

            data = await self._api_request(
                "POST", f"/databases/{self._database_id}/query", json_body=body
            )
            if not data:
                break

            for page in data.get("results", []):
                try:
                    content = await self._get_page_content(page["id"])
                    entity = self.normalize_item({"page": page, "content": content})
                    entities.append(entity)
                except Exception:
                    logger.exception(
                        "Failed to normalize Notion page",
                        extra={"item_id": page.get("id"), "source": "notion"},
                    )

            has_more = data.get("has_more", False)
            start_cursor = data.get("next_cursor")

        return entities

    async def _get_page_content(self, page_id: str) -> str:
        blocks_text: list[str] = []
        has_more = True
        start_cursor: str | None = None

        while has_more:
            url = f"/blocks/{page_id}/children?page_size=100"
            if start_cursor:
                url += f"&start_cursor={start_cursor}"

            data = await self._api_request("GET", url)
            if not data:
                break

            for block in data.get("results", []):
                text = self._extract_block_text(block)
                if text:
                    blocks_text.append(text)

            has_more = data.get("has_more", False)
            start_cursor = data.get("next_cursor")

        return "\n\n".join(blocks_text)

    def _extract_block_text(self, block: dict[str, Any]) -> str:
        block_type = block.get("type", "")
        type_data = block.get(block_type, {})
        if "rich_text" in type_data:
            return "".join(
                rt.get("plain_text", "") for rt in type_data["rich_text"]
            )
        if block_type == "child_page":
            return type_data.get("title", "")
        if block_type in ("image", "video", "file", "pdf"):
            return f"[{block_type}]"
        return ""

    async def _api_request(
        self, method: str, path: str, json_body: dict[str, Any] | None = None
    ) -> dict[str, Any] | None:
        url = f"{NOTION_API_URL}{path}"
        for attempt, backoff in enumerate(RATE_LIMIT_BACKOFF):
            try:
                if method == "POST":
                    response = await self._client.post(url, json=json_body)
                else:
                    response = await self._client.get(url)

                if response.status_code == 429:
                    retry_after = int(response.headers.get("Retry-After", backoff))
                    logger.warning("Notion rate limit, waiting %ds", retry_after)
                    await asyncio.sleep(retry_after)
                    continue
                if response.status_code in (401, 403):
                    logger.error(
                        "Notion auth error (%d): check integration token",
                        response.status_code,
                        extra={"source": "notion", "error_type": "auth"},
                    )
                    return None
                response.raise_for_status()
                return response.json()
            except httpx.HTTPStatusError:
                logger.exception("Notion API error on attempt %d", attempt + 1)
                if attempt < len(RATE_LIMIT_BACKOFF) - 1:
                    await asyncio.sleep(backoff)

        logger.error("Notion API: all retry attempts exhausted")
        return None

    def normalize_item(self, raw: Any) -> Entity:
        page = raw["page"]
        content = raw.get("content", "")

        properties = page.get("properties", {})
        title = self._extract_title(properties)

        # Build a simple "content" key for mapping (blocks text)
        source_values: dict[str, str] = {"content": content, "Title": title}

        fields: list[EntityField] = []
        for source_key, canonical_name in self._field_mappings.items():
            value = source_values.get(source_key, "")
            if canonical_name == "title":
                title = value or title
            else:
                fields.append(
                    EntityField(
                        field_name=canonical_name,
                        field_type="text",
                        field_value=str(value),
                    )
                )
        if not title:
            title = "Untitled"
        if not any(f.field_name == "title" for f in fields):
            fields.insert(
                0,
                EntityField(field_name="title", field_type="text", field_value=title),
            )

        last_edited = page.get("last_edited_time", "")
        created = page.get("created_time", "")

        updated_at = (
            datetime.fromisoformat(last_edited.replace("Z", "+00:00"))
            if last_edited
            else datetime.now(timezone.utc)
        )
        created_at = (
            datetime.fromisoformat(created.replace("Z", "+00:00"))
            if created
            else datetime.now(timezone.utc)
        )

        entity_id = f"notion:{page['id']}"
        return Entity(
            id=entity_id,
            entity_type=EntityType(self._entity_type),
            source_system=SourceSystem.NOTION,
            source_id=page["id"],
            title=title,
            fields=fields,
            chunks=[],
            created_at=created_at,
            updated_at=updated_at,
            is_deleted=False,
        )

    def _extract_title(self, properties: dict[str, Any]) -> str:
        for prop_data in properties.values():
            if prop_data.get("type") == "title":
                title_parts = prop_data.get("title", [])
                return "".join(t.get("plain_text", "") for t in title_parts)
        return "Untitled"

    async def health_check(self) -> bool:
        try:
            result = await self._api_request("GET", "/users/me")
            return result is not None
        except Exception:
            return False

    async def close(self) -> None:
        await self._client.aclose()
