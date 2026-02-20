"""Async SQLite database — CRUD for items and sync state."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from research_agent.storage.models import (
    Base,
    Item,
    ItemRow,
    SyncStateRow,
    item_to_row,
    row_to_item,
)


class Database:
    def __init__(self, db_path: str = "research_agent.db") -> None:
        self._engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}", echo=False)
        self._session_factory = async_sessionmaker(self._engine, expire_on_commit=False)

    async def init(self) -> None:
        async with self._engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def close(self) -> None:
        await self._engine.dispose()

    def session(self) -> AsyncSession:
        return self._session_factory()

    # ------------------------------------------------------------------
    # Item CRUD
    # ------------------------------------------------------------------

    async def upsert_item(self, item: Item) -> bool:
        """Insert or update an item. Returns True if the item was new or changed."""
        async with self.session() as session:
            existing = await session.get(ItemRow, item.id)
            if existing is None:
                session.add(item_to_row(item))
                await session.commit()
                return True

            if existing.content_hash == item.content_hash and existing.is_deleted == item.is_deleted:
                return False

            existing.source = item.source.value
            existing.type = item.type.value
            existing.title = item.title
            existing.body = item.body
            existing.metadata_json = item.metadata
            existing.created_at = item.created_at
            existing.updated_at = datetime.now(timezone.utc)
            existing.content_hash = item.content_hash
            existing.is_deleted = item.is_deleted
            await session.commit()
            return True

    async def get_item(self, item_id: str) -> Item | None:
        async with self.session() as session:
            row = await session.get(ItemRow, item_id)
            return row_to_item(row) if row else None

    async def get_all_items(self, include_deleted: bool = False) -> list[Item]:
        async with self.session() as session:
            stmt = select(ItemRow)
            if not include_deleted:
                stmt = stmt.where(ItemRow.is_deleted == False)  # noqa: E712
            result = await session.execute(stmt)
            return [row_to_item(row) for row in result.scalars().all()]

    async def delete_item(self, item_id: str) -> bool:
        """Soft-delete an item. Returns True if the item existed."""
        async with self.session() as session:
            row = await session.get(ItemRow, item_id)
            if row is None:
                return False
            row.is_deleted = True
            row.updated_at = datetime.now(timezone.utc)
            await session.commit()
            return True

    async def count_items(self, include_deleted: bool = False) -> int:
        async with self.session() as session:
            from sqlalchemy import func

            stmt = select(func.count()).select_from(ItemRow)
            if not include_deleted:
                stmt = stmt.where(ItemRow.is_deleted == False)  # noqa: E712
            result = await session.execute(stmt)
            return result.scalar_one()

    # ------------------------------------------------------------------
    # Sync state (Phase 3, but table created now)
    # ------------------------------------------------------------------

    async def get_sync_state(self, source: str) -> datetime | None:
        async with self.session() as session:
            row = await session.get(SyncStateRow, source)
            return row.last_synced_at if row else None

    async def set_sync_state(self, source: str, synced_at: datetime) -> None:
        async with self.session() as session:
            row = await session.get(SyncStateRow, source)
            if row is None:
                session.add(SyncStateRow(source=source, last_synced_at=synced_at))
            else:
                row.last_synced_at = synced_at
            await session.commit()
