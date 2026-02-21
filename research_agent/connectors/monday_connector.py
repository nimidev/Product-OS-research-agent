"""Monday.com connector — fetches items via GraphQL API, normalizes to Entity using field_mappings."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

import httpx

from research_agent.connectors.base import BaseConnector
from research_agent.storage.models import Entity, EntityField, EntityType, SourceSystem

logger = logging.getLogger(__name__)

MONDAY_API_URL = "https://api.monday.com/v2"
RATE_LIMIT_BACKOFF = [1, 2, 4, 8, 16]
PAGE_SIZE = 100


class MondayConnector(BaseConnector):
    def __init__(
        self,
        api_key: str,
        board_id: int | str,
        entity_type: str | EntityType,
        field_mappings: dict[str, str],
    ) -> None:
        self._api_key = api_key
        self._board_id = int(board_id) if isinstance(board_id, str) else board_id
        self._entity_type = (
            entity_type.value if isinstance(entity_type, EntityType) else entity_type
        )
        self._field_mappings = field_mappings or {"name": "title"}
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

    @property
    def entity_type(self) -> str:
        return self._entity_type

    async def list_updated_items(self, since: datetime | None = None) -> list[Entity]:
        items = await self._fetch_board_items(since)
        return items

    async def _fetch_board_items(self, since: datetime | None = None) -> list[Entity]:
        entities: list[Entity] = []
        cursor: str | None = None
        page = 0

        while True:
            page += 1
            query = self._build_query(cursor)
            data = await self._execute_query(query)

            if not data:
                break

            board_data = data.get("data", {}).get("boards", [{}])[0]
            items_page = board_data.get("items_page", {})
            raw_items = items_page.get("items", [])

            for raw in raw_items:
                try:
                    entity = self.normalize_item(raw)
                    if since and entity.updated_at and entity.updated_at < since:
                        continue
                    entities.append(entity)
                except Exception:
                    logger.exception(
                        "Failed to normalize Monday item",
                        extra={"item_id": raw.get("id"), "source": "monday"},
                    )

            cursor = items_page.get("cursor")
            if not cursor or len(raw_items) < PAGE_SIZE:
                break

            logger.info(
                "Monday board %d: fetched page %d (%d items)",
                self._board_id,
                page,
                len(entities),
            )

        return entities

    def _build_query(self, cursor: str | None = None) -> str:
        cursor_arg = f', cursor: "{cursor}"' if cursor else ""
        return f"""
        query {{
            boards(ids: [{self._board_id}]) {{
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
                        "Monday auth error (%d): check API key",
                        response.status_code,
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

    def normalize_item(self, raw: Any) -> Entity:
        columns = {
            col["id"]: col.get("text", "") or ""
            for col in raw.get("column_values", [])
        }
        # Monday also exposes "name" on the item
        columns["name"] = raw.get("name", "")

        title = ""
        fields: list[EntityField] = []
        for source_col, canonical_name in self._field_mappings.items():
            value = columns.get(source_col, "")
            if canonical_name == "title":
                title = value or title
            else:
                fields.append(
                    EntityField(field_name=canonical_name, field_type="text", field_value=str(value))
                )
        if not title:
            title = raw.get("name", "Untitled")

        # Ensure title is in fields for content_hash
        if not any(f.field_name == "title" for f in fields):
            fields.insert(0, EntityField(field_name="title", field_type="text", field_value=title))

        updated_at = None
        if raw.get("updated_at"):
            try:
                updated_at = datetime.fromisoformat(
                    raw["updated_at"].replace("Z", "+00:00")
                )
            except (ValueError, TypeError):
                pass
        created_at = None
        if raw.get("created_at"):
            try:
                created_at = datetime.fromisoformat(
                    raw["created_at"].replace("Z", "+00:00")
                )
            except (ValueError, TypeError):
                pass

        entity_id = f"monday:{raw['id']}"
        return Entity(
            id=entity_id,
            entity_type=EntityType(self._entity_type),
            source_system=SourceSystem.MONDAY,
            source_id=str(raw["id"]),
            title=title,
            fields=fields,
            chunks=[],  # Sync engine will chunk searchable fields
            created_at=created_at or datetime.now(timezone.utc),
            updated_at=updated_at or datetime.now(timezone.utc),
            is_deleted=False,
        )

    async def health_check(self) -> bool:
        try:
            result = await self._execute_query("query { me { id } }")
            return result is not None and "data" in result
        except Exception:
            return False

    async def close(self) -> None:
        await self._client.aclose()
