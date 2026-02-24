"""Async SQLite database — CRUD for entities, fields, chunks, and sync state."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from research_agent.storage.models import (
    Base,
    ChunkRow,
    Entity,
    EntityFieldRow,
    EntityRow,
    IntegrationConfigRow,
    SyncStateRow,
    entity_to_rows,
    rows_to_entity,
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
    # Entity CRUD
    # ------------------------------------------------------------------

    async def upsert_entity(self, entity: Entity) -> bool:
        """Insert or update an entity with its fields and chunks.

        Returns True if the entity was new or changed.
        """
        e_row, f_rows, c_rows = entity_to_rows(entity)

        async with self.session() as session:
            existing = await session.get(EntityRow, entity.id)

            if existing is None:
                session.add(e_row)
                session.add_all(f_rows)
                session.add_all(c_rows)
                await session.commit()
                return True

            if (
                existing.content_hash == entity.content_hash
                and existing.is_deleted == entity.is_deleted
            ):
                return False

            existing.entity_type = entity.entity_type.value
            existing.source_system = entity.source_system.value
            existing.source_id = entity.source_id
            existing.title = entity.title
            existing.updated_at = datetime.now(UTC)
            existing.content_hash = entity.content_hash
            existing.is_deleted = entity.is_deleted

            await session.execute(
                delete(EntityFieldRow).where(EntityFieldRow.entity_id == entity.id)
            )
            await session.execute(
                delete(ChunkRow).where(ChunkRow.entity_id == entity.id)
            )
            session.add_all(f_rows)
            session.add_all(c_rows)
            await session.commit()
            return True

    async def get_entity(self, entity_id: str) -> Entity | None:
        async with self.session() as session:
            row = await session.get(EntityRow, entity_id)
            if row is None:
                return None
            f_rows = (
                await session.execute(
                    select(EntityFieldRow).where(EntityFieldRow.entity_id == entity_id)
                )
            ).scalars().all()
            c_rows = (
                await session.execute(
                    select(ChunkRow).where(ChunkRow.entity_id == entity_id)
                )
            ).scalars().all()
            return rows_to_entity(row, list(f_rows), list(c_rows))

    async def get_all_entities(
        self,
        include_deleted: bool = False,
        entity_type: str | None = None,
    ) -> list[Entity]:
        async with self.session() as session:
            stmt = select(EntityRow)
            if not include_deleted:
                stmt = stmt.where(EntityRow.is_deleted == False)  # noqa: E712
            if entity_type:
                stmt = stmt.where(EntityRow.entity_type == entity_type)
            result = await session.execute(stmt)
            entities: list[Entity] = []
            for row in result.scalars().all():
                f_rows = (
                    await session.execute(
                        select(EntityFieldRow).where(EntityFieldRow.entity_id == row.id)
                    )
                ).scalars().all()
                c_rows = (
                    await session.execute(
                        select(ChunkRow).where(ChunkRow.entity_id == row.id)
                    )
                ).scalars().all()
                entities.append(rows_to_entity(row, list(f_rows), list(c_rows)))
            return entities

    async def delete_entity(self, entity_id: str) -> bool:
        """Soft-delete an entity. Returns True if the entity existed."""
        async with self.session() as session:
            row = await session.get(EntityRow, entity_id)
            if row is None:
                return False
            row.is_deleted = True
            row.updated_at = datetime.now(UTC)
            await session.commit()
            return True

    async def count_entities(self, include_deleted: bool = False) -> int:
        async with self.session() as session:
            from sqlalchemy import func

            stmt = select(func.count()).select_from(EntityRow)
            if not include_deleted:
                stmt = stmt.where(EntityRow.is_deleted == False)  # noqa: E712
            result = await session.execute(stmt)
            return result.scalar_one()

    # ------------------------------------------------------------------
    # Sync state
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

    # ------------------------------------------------------------------
    # Integration config
    # ------------------------------------------------------------------

    async def get_integration_config(self, source: str) -> dict | None:
        async with self.session() as session:
            row = await session.get(IntegrationConfigRow, source)
            if row is None:
                return None
            return {
                "source": row.source,
                "enabled": row.enabled,
                "api_key": row.api_key,
                "board_ids": json.loads(row.board_ids_json or "[]"),
                "entity_mappings": json.loads(row.entity_mappings_json or "{}"),
                "sync_interval_seconds": row.sync_interval_seconds,
                "updated_at": row.updated_at,
            }

    async def upsert_integration_config(
        self,
        source: str,
        enabled: bool,
        board_ids: list[str],
        entity_mappings: dict[str, str],
        sync_interval_seconds: int,
        api_key: str | None = None,
    ) -> dict:
        async with self.session() as session:
            row = await session.get(IntegrationConfigRow, source)
            now = datetime.now(UTC)
            if row is None:
                row = IntegrationConfigRow(
                    source=source,
                    enabled=enabled,
                    api_key=api_key or "",
                    board_ids_json=json.dumps(board_ids),
                    entity_mappings_json=json.dumps(entity_mappings),
                    sync_interval_seconds=sync_interval_seconds,
                    updated_at=now,
                )
                session.add(row)
            else:
                row.enabled = enabled
                if api_key is not None:
                    row.api_key = api_key
                row.board_ids_json = json.dumps(board_ids)
                row.entity_mappings_json = json.dumps(entity_mappings)
                row.sync_interval_seconds = sync_interval_seconds
                row.updated_at = now

            await session.commit()

        config = await self.get_integration_config(source)
        assert config is not None
        return config
