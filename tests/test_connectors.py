"""Tests for connector interface and implementations."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from research_agent.connectors.base import BaseConnector
from research_agent.connectors.monday_connector import MondayConnector
from research_agent.connectors.notion_connector import NotionConnector
from research_agent.storage.models import Entity, EntityType, SourceSystem


class TestBaseConnector:
    def test_abstract_class(self):
        with pytest.raises(TypeError):
            BaseConnector()  # type: ignore[abstract]


class TestMondayConnector:
    def test_normalize_item(self):
        connector = MondayConnector(
            api_key="test",
            board_id=1,
            entity_type="feature_request",
            field_mappings={"name": "title", "description": "description", "priority": "priority"},
        )
        raw = {
            "id": "12345",
            "name": "Add SSO support",
            "created_at": "2025-06-15T10:00:00Z",
            "updated_at": "2025-07-01T14:00:00Z",
            "column_values": [
                {"id": "description", "text": "Enterprise SSO needed"},
                {"id": "priority", "text": "High"},
            ],
            "group": {"title": "Feature Requests"},
        }
        entity = connector.normalize_item(raw)
        assert entity.id == "monday:12345"
        assert entity.source_system == SourceSystem.MONDAY
        assert entity.title == "Add SSO support"
        assert entity.entity_type == EntityType.FEATURE_REQUEST
        assert entity.get_field("description") == "Enterprise SSO needed"
        assert entity.get_field("priority") == "High"

    def test_normalize_bug(self):
        connector = MondayConnector(
            api_key="test",
            board_id=1,
            entity_type="bug",
            field_mappings={"name": "title"},
        )
        raw = {
            "id": "99",
            "name": "Login broken",
            "column_values": [],
            "group": {"title": "Bugs"},
        }
        entity = connector.normalize_item(raw)
        assert entity.entity_type == EntityType.BUG

    def test_source_name(self):
        connector = MondayConnector(
            api_key="test",
            board_id=1,
            entity_type="feature_request",
            field_mappings={"name": "title"},
        )
        assert connector.source_name == "monday"

    def test_entity_type(self):
        connector = MondayConnector(
            api_key="test",
            board_id=1,
            entity_type="roadmap_item",
            field_mappings={},
        )
        assert connector.entity_type == "roadmap_item"

    @pytest.mark.asyncio
    async def test_health_check_failure(self):
        connector = MondayConnector(
            api_key="bad-key",
            board_id=1,
            entity_type="feature_request",
            field_mappings={"name": "title"},
        )
        connector._client = AsyncMock()
        connector._client.post = AsyncMock(side_effect=Exception("connection error"))
        result = await connector.health_check()
        assert result is False


class TestNotionConnector:
    def test_normalize_item(self):
        connector = NotionConnector(
            api_key="test",
            database_id="db1",
            entity_type="prd",
            field_mappings={"Title": "title", "content": "overview"},
        )
        raw = {
            "page": {
                "id": "abc-123",
                "url": "https://notion.so/abc-123",
                "created_time": "2025-06-15T10:00:00.000Z",
                "last_edited_time": "2025-07-01T14:00:00.000Z",
                "properties": {
                    "Name": {
                        "type": "title",
                        "title": [{"plain_text": "Auth redesign PRD"}],
                    },
                    "Tags": {
                        "type": "multi_select",
                        "multi_select": [
                            {"name": "PRD"},
                            {"name": "Auth"},
                        ],
                    },
                },
            },
            "content": "Full page content about auth redesign...",
        }
        entity = connector.normalize_item(raw)
        assert entity.id == "notion:abc-123"
        assert entity.source_system == SourceSystem.NOTION
        assert entity.title == "Auth redesign PRD"
        assert entity.entity_type == EntityType.PRD
        assert entity.get_field("overview") == "Full page content about auth redesign..."

    def test_source_name(self):
        connector = NotionConnector(
            api_key="test",
            database_id="db1",
            entity_type="meeting_note",
            field_mappings={"content": "transcript"},
        )
        assert connector.source_name == "notion"

    def test_extract_block_text_paragraph(self):
        connector = NotionConnector(
            api_key="test",
            database_id="db1",
            entity_type="meeting_note",
            field_mappings={},
        )
        block = {
            "type": "paragraph",
            "paragraph": {
                "rich_text": [{"plain_text": "Hello "}, {"plain_text": "world"}]
            },
        }
        assert connector._extract_block_text(block) == "Hello world"

    def test_extract_block_text_image(self):
        connector = NotionConnector(
            api_key="test",
            database_id="db1",
            entity_type="meeting_note",
            field_mappings={},
        )
        block = {"type": "image", "image": {}}
        assert connector._extract_block_text(block) == "[image]"
