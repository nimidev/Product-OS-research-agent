"""Tests for canonical entity model and SQLite CRUD."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from research_agent.storage.db import Database
from research_agent.storage.models import (
    Entity,
    EntityField,
    EntityType,
    SourceSystem,
    compute_content_hash,
)
from tests.conftest import make_entity


@pytest.fixture
async def db(tmp_path):
    database = Database(db_path=str(tmp_path / "test.db"))
    await database.init()
    yield database
    await database.close()


class TestContentHash:
    def test_deterministic(self):
        h1 = compute_content_hash({"title": "t", "a": "b"})
        h2 = compute_content_hash({"title": "t", "a": "b"})
        assert h1 == h2

    def test_changes_with_content(self):
        h1 = compute_content_hash({"title": "t", "body": "x"})
        h2 = compute_content_hash({"title": "t", "body": "y"})
        assert h1 != h2

    def test_entity_content_hash(self):
        entity = make_entity()
        assert len(entity.content_hash) == 64


class TestEntityModel:
    def test_all_fields_present(self):
        entity = make_entity()
        assert entity.id == "mock:feature_request:001"
        assert entity.source_system == SourceSystem.MOCK
        assert entity.entity_type == EntityType.FEATURE_REQUEST
        assert entity.title == "Add dark mode"
        assert entity.get_field("description") == "Users want a dark mode option."
        assert entity.is_deleted is False
        assert len(entity.content_hash) == 64

    def test_source_enum_values(self):
        assert SourceSystem.MOCK == "mock"
        assert SourceSystem.MONDAY == "monday"
        assert SourceSystem.NOTION == "notion"

    def test_entity_type_enum_values(self):
        assert EntityType.FEATURE_REQUEST == "feature_request"
        assert EntityType.BUG == "bug"
        assert EntityType.MEETING_NOTE == "meeting_note"
        assert EntityType.PRD == "prd"
        assert EntityType.ROADMAP_ITEM == "roadmap_item"
        assert EntityType.SUPPORT_TICKET == "support_ticket"


class TestDatabaseCRUD:
    @pytest.mark.asyncio
    async def test_insert_and_get(self, db):
        entity = make_entity()
        changed = await db.upsert_entity(entity)
        assert changed is True

        retrieved = await db.get_entity(entity.id)
        assert retrieved is not None
        assert retrieved.id == entity.id
        assert retrieved.title == entity.title
        assert retrieved.source_system == entity.source_system
        assert retrieved.entity_type == entity.entity_type
        assert retrieved.content_hash == entity.content_hash

    @pytest.mark.asyncio
    async def test_upsert_no_change(self, db):
        entity = make_entity()
        await db.upsert_entity(entity)

        changed = await db.upsert_entity(entity)
        assert changed is False

    @pytest.mark.asyncio
    async def test_upsert_with_change(self, db):
        entity = make_entity()
        await db.upsert_entity(entity)

        updated = make_entity()
        updated.fields = [
            EntityField(field_name="title", field_type="text", field_value=entity.title),
            EntityField(field_name="description", field_type="text", field_value="Updated: users really want dark mode with OLED support."),
        ]
        changed = await db.upsert_entity(updated)
        assert changed is True

        retrieved = await db.get_entity(entity.id)
        assert retrieved is not None
        assert retrieved.get_field("description") == updated.get_field("description")
        assert retrieved.content_hash == updated.content_hash

    @pytest.mark.asyncio
    async def test_get_nonexistent(self, db):
        result = await db.get_entity("nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_soft_delete(self, db):
        entity = make_entity()
        await db.upsert_entity(entity)

        deleted = await db.delete_entity(entity.id)
        assert deleted is True

        active = await db.get_all_entities(include_deleted=False)
        assert len(active) == 0

        all_entities = await db.get_all_entities(include_deleted=True)
        assert len(all_entities) == 1
        assert all_entities[0].is_deleted is True

    @pytest.mark.asyncio
    async def test_delete_nonexistent(self, db):
        result = await db.delete_entity("nonexistent")
        assert result is False

    @pytest.mark.asyncio
    async def test_get_all_entities(self, db):
        for i in range(5):
            await db.upsert_entity(make_entity(id=f"mock:feature_request:{i:03d}", title=f"FR {i}"))

        entities = await db.get_all_entities()
        assert len(entities) == 5

    @pytest.mark.asyncio
    async def test_count_entities(self, db):
        for i in range(3):
            await db.upsert_entity(make_entity(id=f"mock:bug:{i:03d}", title=f"Bug {i}"))

        assert await db.count_entities() == 3
        await db.delete_entity("mock:bug:001")
        assert await db.count_entities() == 2
        assert await db.count_entities(include_deleted=True) == 3

    @pytest.mark.asyncio
    async def test_fields_persist(self, db):
        entity = make_entity()
        entity.fields.append(EntityField(field_name="customer", field_type="text", field_value="Acme Corp"))
        entity.fields.append(EntityField(field_name="votes", field_type="text", field_value="42"))
        await db.upsert_entity(entity)

        retrieved = await db.get_entity(entity.id)
        assert retrieved is not None
        assert retrieved.get_field("customer") == "Acme Corp"
        assert retrieved.get_field("votes") == "42"


class TestSyncState:
    @pytest.mark.asyncio
    async def test_get_unset(self, db):
        result = await db.get_sync_state("monday")
        assert result is None

    @pytest.mark.asyncio
    async def test_set_and_get(self, db):
        ts = datetime(2025, 7, 1, 12, 0, 0, tzinfo=timezone.utc)
        await db.set_sync_state("monday", ts)
        result = await db.get_sync_state("monday")
        assert result is not None
        assert result.replace(tzinfo=None) == ts.replace(tzinfo=None)

    @pytest.mark.asyncio
    async def test_update(self, db):
        ts1 = datetime(2025, 7, 1, tzinfo=timezone.utc)
        ts2 = datetime(2025, 7, 2, tzinfo=timezone.utc)
        await db.set_sync_state("notion", ts1)
        await db.set_sync_state("notion", ts2)
        result = await db.get_sync_state("notion")
        assert result is not None
        assert result.replace(tzinfo=None) == ts2.replace(tzinfo=None)


class TestIntegrationConfig:
    @pytest.mark.asyncio
    async def test_upsert_and_get_jira_config_with_site_url(self, db):
        await db.upsert_integration_config(
            source="jira",
            enabled=True,
            board_ids=[],
            entity_mappings={},
            sync_interval_seconds=7200,
            api_key="token",
            subdomain="cloud-123",
            site_url="https://my.atlassian.net",
        )
        config = await db.get_integration_config("jira")
        assert config is not None
        assert config["source"] == "jira"
        assert config["subdomain"] == "cloud-123"
        assert config.get("site_url") == "https://my.atlassian.net"

    @pytest.mark.asyncio
    async def test_upsert_jira_config_site_url_optional(self, db):
        await db.upsert_integration_config(
            source="jira",
            enabled=True,
            board_ids=[],
            entity_mappings={},
            sync_interval_seconds=7200,
            api_key="token",
            subdomain="cloud-1",
            # site_url not passed
        )
        config = await db.get_integration_config("jira")
        assert config is not None
        assert config.get("site_url") is None
