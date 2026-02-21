"""Canonical entity schema — entities + entity_fields + chunks."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class SourceSystem(StrEnum):
    MOCK = "mock"
    MONDAY = "monday"
    NOTION = "notion"


class EntityType(StrEnum):
    FEATURE_REQUEST = "feature_request"
    ROADMAP_ITEM = "roadmap_item"
    SUPPORT_TICKET = "support_ticket"
    BUG = "bug"
    PRD = "prd"
    MEETING_NOTE = "meeting_note"


CANONICAL_FIELDS: dict[EntityType, list[str]] = {
    EntityType.FEATURE_REQUEST: [
        "title", "description", "customer", "priority", "status", "votes",
    ],
    EntityType.ROADMAP_ITEM: [
        "title", "description", "target_start", "target_end", "status", "priority",
    ],
    EntityType.SUPPORT_TICKET: [
        "title", "description", "customer", "priority", "status", "resolution",
    ],
    EntityType.BUG: [
        "title", "description", "severity", "status", "affected_version", "priority",
    ],
    EntityType.PRD: [
        "title", "overview", "target_users", "requirements", "success_metrics", "status",
    ],
    EntityType.MEETING_NOTE: [
        "title", "transcript", "summary", "attendees", "date", "tags",
    ],
}


def compute_content_hash(fields: dict[str, str]) -> str:
    """Hash all field values for change detection."""
    parts = sorted(f"{k}={v}" for k, v in fields.items())
    return hashlib.sha256("\n".join(parts).encode()).hexdigest()


# ---------------------------------------------------------------------------
# SQLAlchemy ORM models
# ---------------------------------------------------------------------------

class Base(DeclarativeBase):
    pass


class EntityRow(Base):
    __tablename__ = "entities"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    entity_type: Mapped[str] = mapped_column(String, nullable=False, index=True)
    source_system: Mapped[str] = mapped_column(String, nullable=False, index=True)
    source_id: Mapped[str] = mapped_column(String, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc),
    )
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    is_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    fields_: Mapped[list[EntityFieldRow]] = relationship(
        back_populates="entity", cascade="all, delete-orphan",
    )
    chunks: Mapped[list[ChunkRow]] = relationship(
        back_populates="entity", cascade="all, delete-orphan",
    )


class EntityFieldRow(Base):
    __tablename__ = "entity_fields"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    entity_id: Mapped[str] = mapped_column(
        String, ForeignKey("entities.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    field_name: Mapped[str] = mapped_column(String, nullable=False)
    field_type: Mapped[str] = mapped_column(String, nullable=False, default="text")
    field_value: Mapped[str] = mapped_column(Text, nullable=False, default="")

    entity: Mapped[EntityRow] = relationship(back_populates="fields_")


class ChunkRow(Base):
    __tablename__ = "chunks"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    entity_id: Mapped[str] = mapped_column(
        String, ForeignKey("entities.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    field_name: Mapped[str] = mapped_column(String, nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    text: Mapped[str] = mapped_column(Text, nullable=False)

    entity: Mapped[EntityRow] = relationship(back_populates="chunks")


class SyncStateRow(Base):
    __tablename__ = "sync_state"

    source: Mapped[str] = mapped_column(String, primary_key=True)
    last_synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


# ---------------------------------------------------------------------------
# Pydantic DTOs
# ---------------------------------------------------------------------------

class EntityField(BaseModel):
    field_name: str
    field_type: str = "text"
    field_value: str = ""


class Chunk(BaseModel):
    id: str = ""
    field_name: str
    chunk_index: int = 0
    text: str


class Entity(BaseModel):
    id: str
    entity_type: EntityType
    source_system: SourceSystem
    source_id: str
    title: str
    fields: list[EntityField] = Field(default_factory=list)
    chunks: list[Chunk] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    is_deleted: bool = False

    @property
    def content_hash(self) -> str:
        field_dict = {f.field_name: f.field_value for f in self.fields}
        field_dict["title"] = self.title
        return compute_content_hash(field_dict)

    def get_field(self, name: str) -> str | None:
        for f in self.fields:
            if f.field_name == name:
                return f.field_value
        return None

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Conversion helpers
# ---------------------------------------------------------------------------

def entity_to_rows(
    entity: Entity,
) -> tuple[EntityRow, list[EntityFieldRow], list[ChunkRow]]:
    e_row = EntityRow(
        id=entity.id,
        entity_type=entity.entity_type.value,
        source_system=entity.source_system.value,
        source_id=entity.source_id,
        title=entity.title,
        created_at=entity.created_at,
        updated_at=entity.updated_at,
        content_hash=entity.content_hash,
        is_deleted=entity.is_deleted,
    )
    f_rows = [
        EntityFieldRow(
            entity_id=entity.id,
            field_name=f.field_name,
            field_type=f.field_type,
            field_value=f.field_value,
        )
        for f in entity.fields
    ]
    c_rows = [
        ChunkRow(
            id=c.id or f"{entity.id}:{c.field_name}:{c.chunk_index}",
            entity_id=entity.id,
            field_name=c.field_name,
            chunk_index=c.chunk_index,
            text=c.text,
        )
        for c in entity.chunks
    ]
    return e_row, f_rows, c_rows


def rows_to_entity(
    row: EntityRow,
    field_rows: list[EntityFieldRow] | None = None,
    chunk_rows: list[ChunkRow] | None = None,
) -> Entity:
    _field_rows = field_rows if field_rows is not None else row.fields_
    _chunk_rows = chunk_rows if chunk_rows is not None else row.chunks
    fields = [
        EntityField(
            field_name=f.field_name,
            field_type=f.field_type,
            field_value=f.field_value,
        )
        for f in _field_rows
    ]
    chunks = [
        Chunk(
            id=c.id,
            field_name=c.field_name,
            chunk_index=c.chunk_index,
            text=c.text,
        )
        for c in _chunk_rows
    ]
    return Entity(
        id=row.id,
        entity_type=EntityType(row.entity_type),
        source_system=SourceSystem(row.source_system),
        source_id=row.source_id,
        title=row.title,
        fields=fields,
        chunks=chunks,
        created_at=row.created_at,
        updated_at=row.updated_at,
        is_deleted=row.is_deleted,
    )


# ---------------------------------------------------------------------------
# Backward-compat aliases for imports that haven't migrated yet
# ---------------------------------------------------------------------------

ItemSource = SourceSystem
ItemType = EntityType
