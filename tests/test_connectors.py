"""Tests for connector interface and implementations."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from research_agent.connectors.base import BaseConnector, NormalizedItem
from research_agent.connectors.monday_connector import MondayConnector
from research_agent.connectors.notion_connector import NotionConnector


class TestBaseConnector:
    def test_normalized_item_creation(self):
        item = NormalizedItem(
            id="test:001",
            source="test",
            type="feature_request",
            title="Test Item",
            body="Test body",
            metadata={"tags": ["test"]},
        )
        assert item.id == "test:001"
        assert item.source == "test"
        assert item.is_deleted is False

    def test_abstract_class(self):
        with pytest.raises(TypeError):
            BaseConnector()  # type: ignore[abstract]


class TestMondayConnector:
    def test_normalize_item(self):
        connector = MondayConnector(api_key="test", board_ids=[1])
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
        item = connector.normalize_item(raw)
        assert item.id == "monday:12345"
        assert item.source == "monday"
        assert item.title == "Add SSO support"
        assert item.type == "feature_request"

    def test_normalize_bug(self):
        connector = MondayConnector(api_key="test", board_ids=[1])
        raw = {
            "id": "99",
            "name": "Login broken",
            "column_values": [],
            "group": {"title": "Bugs"},
        }
        item = connector.normalize_item(raw)
        assert item.type == "bug"

    def test_source_name(self):
        connector = MondayConnector(api_key="test", board_ids=[])
        assert connector.source_name == "monday"

    @pytest.mark.asyncio
    async def test_health_check_failure(self):
        connector = MondayConnector(api_key="bad-key", board_ids=[])
        connector._client = AsyncMock()
        connector._client.post = AsyncMock(side_effect=Exception("connection error"))
        result = await connector.health_check()
        assert result is False


class TestNotionConnector:
    def test_normalize_item(self):
        connector = NotionConnector(api_key="test", database_ids=["db1"])
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
        item = connector.normalize_item(raw)
        assert item.id == "notion:abc-123"
        assert item.source == "notion"
        assert item.title == "Auth redesign PRD"
        assert item.type == "prd"
        assert "PRD" in item.metadata["tags"]

    def test_source_name(self):
        connector = NotionConnector(api_key="test", database_ids=[])
        assert connector.source_name == "notion"

    def test_extract_block_text_paragraph(self):
        connector = NotionConnector(api_key="test", database_ids=[])
        block = {
            "type": "paragraph",
            "paragraph": {
                "rich_text": [{"plain_text": "Hello "}, {"plain_text": "world"}]
            },
        }
        assert connector._extract_block_text(block) == "Hello world"

    def test_extract_block_text_image(self):
        connector = NotionConnector(api_key="test", database_ids=[])
        block = {"type": "image", "image": {}}
        assert connector._extract_block_text(block) == "[image]"
