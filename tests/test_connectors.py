"""Tests for connector interface and implementations."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from research_agent.connectors.base import BaseConnector
from research_agent.connectors.jira_connector import JiraConnector
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


class TestJiraConnector:
    def _make_connector(self, **kwargs):
        defaults = dict(
            access_token="test-token",
            cloud_id="test-cloud-id",
            project_key="PROJ",
            issue_type_names=["Story", "Bug"],
            entity_type="feature_request",
            field_mappings={"summary": "title", "description": "description", "priority": "priority"},
        )
        defaults.update(kwargs)
        return JiraConnector(**defaults)

    def test_normalize_item(self):
        connector = self._make_connector()
        raw = {
            "key": "PROJ-42",
            "id": "10042",
            "fields": {
                "summary": "Add SSO support",
                "description": {"type": "doc", "content": [{"type": "text", "text": "Enterprise SSO needed"}]},
                "priority": {"name": "High"},
                "status": {"name": "Open"},
                "issuetype": {"name": "Story"},
                "created": "2025-06-15T10:00:00.000+0000",
                "updated": "2025-07-01T14:00:00.000+0000",
            },
        }
        entity = connector.normalize_item(raw)
        assert entity.id == "jira:PROJ-42"
        assert entity.source_system == SourceSystem.JIRA
        assert entity.entity_type == EntityType.FEATURE_REQUEST
        assert entity.title == "Add SSO support"
        assert entity.source_id == "PROJ-42"
        assert entity.get_field("description") == "Enterprise SSO needed"
        assert entity.get_field("priority") == "High"

    def test_normalize_bug(self):
        connector = self._make_connector(entity_type="bug")
        raw = {
            "key": "PROJ-99",
            "fields": {
                "summary": "Login broken",
                "issuetype": {"name": "Bug"},
            },
        }
        entity = connector.normalize_item(raw)
        assert entity.entity_type == EntityType.BUG
        assert entity.title == "Login broken"

    def test_source_name(self):
        connector = self._make_connector()
        assert connector.source_name == "jira"

    def test_entity_type(self):
        connector = self._make_connector(entity_type="roadmap_item")
        assert connector.entity_type == "roadmap_item"

    def test_sync_state_key(self):
        connector = self._make_connector()
        assert connector.sync_state_key == "jira:test-cloud-id:PROJ:feature_request"

    def test_sync_state_key_with_board(self):
        connector = self._make_connector(board_id=42)
        assert "board:42" in connector.sync_state_key

    def test_extract_adf_text(self):
        doc = {
            "type": "doc",
            "content": [
                {
                    "type": "paragraph",
                    "content": [
                        {"type": "text", "text": "Hello "},
                        {"type": "text", "text": "world"},
                    ],
                }
            ],
        }
        assert JiraConnector._extract_adf_text(doc) == "Hello \nworld"

    def test_extract_field_value_string(self):
        assert JiraConnector._extract_field_value({"f": "hello"}, "f") == "hello"

    def test_extract_field_value_dict_name(self):
        assert JiraConnector._extract_field_value({"f": {"name": "High"}}, "f") == "High"

    def test_extract_field_value_list(self):
        result = JiraConnector._extract_field_value(
            {"f": [{"name": "A"}, {"name": "B"}]}, "f"
        )
        assert result == "A, B"

    def test_extract_field_value_none(self):
        assert JiraConnector._extract_field_value({}, "missing") == ""

    def test_matches_issue_types_filter(self):
        connector = self._make_connector(issue_type_names=["Story"])
        raw_match = {"fields": {"issuetype": {"name": "Story"}}}
        raw_miss = {"fields": {"issuetype": {"name": "Epic"}}}
        assert connector._matches_issue_types(raw_match) is True
        assert connector._matches_issue_types(raw_miss) is False

    def test_matches_issue_types_no_filter(self):
        connector = self._make_connector(issue_type_names=[])
        raw = {"fields": {"issuetype": {"name": "Whatever"}}}
        assert connector._matches_issue_types(raw) is True

    @pytest.mark.asyncio
    async def test_health_check_failure(self):
        connector = self._make_connector()
        connector._client = AsyncMock()
        connector._client.request = AsyncMock(side_effect=Exception("connection error"))
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
