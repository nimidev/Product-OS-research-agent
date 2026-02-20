"""Tests for canonical data model and SQLite CRUD."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from research_agent.storage.db import Database
from research_agent.storage.models import Item, ItemSource, ItemType, compute_content_hash


@pytest.fixture
async def db(tmp_path):
    database = Database(db_path=str(tmp_path / "test.db"))
    await database.init()
    yield database
    await database.close()


def _make_item(
    id: str = "mock:feature_request:001",
    title: str = "Add dark mode",
    body: str = "Users want a dark mode option for the app.",
    **kwargs,
) -> Item:
    defaults = {
        "source": ItemSource.MOCK,
        "type": ItemType.FEATURE_REQUEST,
        "metadata": {"tags": ["ui", "theme"], "priority": "high"},
        "created_at": datetime(2025, 6, 15, tzinfo=timezone.utc),
        "updated_at": datetime(2025, 6, 15, tzinfo=timezone.utc),
    }
    defaults.update(kwargs)
    return Item(id=id, title=title, body=body, **defaults)


class TestContentHash:
    def test_deterministic(self):
        h1 = compute_content_hash("title", "body")
        h2 = compute_content_hash("title", "body")
        assert h1 == h2

    def test_changes_with_content(self):
        h1 = compute_content_hash("title", "body")
        h2 = compute_content_hash("title", "different body")
        assert h1 != h2

    def test_item_computed_hash(self):
        item = _make_item()
        assert item.content_hash == compute_content_hash(item.title, item.body)


class TestItemModel:
    def test_all_fields_present(self):
        item = _make_item()
        assert item.id == "mock:feature_request:001"
        assert item.source == ItemSource.MOCK
        assert item.type == ItemType.FEATURE_REQUEST
        assert item.title == "Add dark mode"
        assert item.body == "Users want a dark mode option for the app."
        assert item.metadata["tags"] == ["ui", "theme"]
        assert item.is_deleted is False
        assert len(item.content_hash) == 64

    def test_source_enum_values(self):
        assert ItemSource.MOCK == "mock"
        assert ItemSource.MONDAY == "monday"
        assert ItemSource.NOTION == "notion"

    def test_type_enum_values(self):
        assert ItemType.FEATURE_REQUEST == "feature_request"
        assert ItemType.BUG == "bug"
        assert ItemType.MEETING_NOTE == "meeting_note"
        assert ItemType.PRD == "prd"
        assert ItemType.ROADMAP_ITEM == "roadmap_item"
        assert ItemType.SUPPORT_TICKET == "support_ticket"


class TestDatabaseCRUD:
    @pytest.mark.asyncio
    async def test_insert_and_get(self, db):
        item = _make_item()
        changed = await db.upsert_item(item)
        assert changed is True

        retrieved = await db.get_item(item.id)
        assert retrieved is not None
        assert retrieved.id == item.id
        assert retrieved.title == item.title
        assert retrieved.body == item.body
        assert retrieved.source == item.source
        assert retrieved.type == item.type
        assert retrieved.content_hash == item.content_hash

    @pytest.mark.asyncio
    async def test_upsert_no_change(self, db):
        item = _make_item()
        await db.upsert_item(item)

        changed = await db.upsert_item(item)
        assert changed is False

    @pytest.mark.asyncio
    async def test_upsert_with_change(self, db):
        item = _make_item()
        await db.upsert_item(item)

        updated = _make_item(body="Updated: users really want dark mode with OLED support.")
        changed = await db.upsert_item(updated)
        assert changed is True

        retrieved = await db.get_item(item.id)
        assert retrieved is not None
        assert retrieved.body == updated.body
        assert retrieved.content_hash == updated.content_hash

    @pytest.mark.asyncio
    async def test_get_nonexistent(self, db):
        result = await db.get_item("nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_soft_delete(self, db):
        item = _make_item()
        await db.upsert_item(item)

        deleted = await db.delete_item(item.id)
        assert deleted is True

        active_items = await db.get_all_items(include_deleted=False)
        assert len(active_items) == 0

        all_items = await db.get_all_items(include_deleted=True)
        assert len(all_items) == 1
        assert all_items[0].is_deleted is True

    @pytest.mark.asyncio
    async def test_delete_nonexistent(self, db):
        result = await db.delete_item("nonexistent")
        assert result is False

    @pytest.mark.asyncio
    async def test_get_all_items(self, db):
        for i in range(5):
            await db.upsert_item(_make_item(id=f"mock:feature_request:{i:03d}", title=f"FR {i}"))

        items = await db.get_all_items()
        assert len(items) == 5

    @pytest.mark.asyncio
    async def test_count_items(self, db):
        for i in range(3):
            await db.upsert_item(_make_item(id=f"mock:bug:{i:03d}", title=f"Bug {i}"))

        assert await db.count_items() == 3
        await db.delete_item("mock:bug:001")
        assert await db.count_items() == 2
        assert await db.count_items(include_deleted=True) == 3

    @pytest.mark.asyncio
    async def test_metadata_persists(self, db):
        item = _make_item(metadata={"customer": "Acme Corp", "votes": 42, "tags": ["urgent"]})
        await db.upsert_item(item)

        retrieved = await db.get_item(item.id)
        assert retrieved is not None
        assert retrieved.metadata["customer"] == "Acme Corp"
        assert retrieved.metadata["votes"] == 42
        assert retrieved.metadata["tags"] == ["urgent"]


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
