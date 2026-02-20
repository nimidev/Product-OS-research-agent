"""Canonical Item schema — the single source of truth for all organizational data."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, computed_field
from sqlalchemy import JSON, Boolean, DateTime, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class ItemSource(StrEnum):
    MOCK = "mock"
    MONDAY = "monday"
    NOTION = "notion"


class ItemType(StrEnum):
    ROADMAP_ITEM = "roadmap_item"
    FEATURE_REQUEST = "feature_request"
    SUPPORT_TICKET = "support_ticket"
    BUG = "bug"
    PRD = "prd"
    MEETING_NOTE = "meeting_note"


def compute_content_hash(title: str, body: str) -> str:
    return hashlib.sha256(f"{title}\n{body}".encode()).hexdigest()


# ---------------------------------------------------------------------------
# SQLAlchemy ORM model
# ---------------------------------------------------------------------------

class Base(DeclarativeBase):
    pass


class ItemRow(Base):
    __tablename__ = "items"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    source: Mapped[str] = mapped_column(String, nullable=False, index=True)
    type: Mapped[str] = mapped_column(String, nullable=False, index=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False, default="")
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSON, nullable=False, default=dict
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    is_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class SyncStateRow(Base):
    """Tracks last sync timestamp per source (Phase 3)."""

    __tablename__ = "sync_state"

    source: Mapped[str] = mapped_column(String, primary_key=True)
    last_synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


# ---------------------------------------------------------------------------
# Pydantic DTO — used across the codebase for passing items around
# ---------------------------------------------------------------------------

class Item(BaseModel):
    id: str
    source: ItemSource
    type: ItemType
    title: str
    body: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    is_deleted: bool = False

    @computed_field  # type: ignore[prop-decorator]
    @property
    def content_hash(self) -> str:
        return compute_content_hash(self.title, self.body)

    model_config = {"from_attributes": True}


def item_to_row(item: Item) -> ItemRow:
    return ItemRow(
        id=item.id,
        source=item.source.value,
        type=item.type.value,
        title=item.title,
        body=item.body,
        metadata_json=item.metadata,
        created_at=item.created_at,
        updated_at=item.updated_at,
        content_hash=item.content_hash,
        is_deleted=item.is_deleted,
    )


def row_to_item(row: ItemRow) -> Item:
    return Item(
        id=row.id,
        source=ItemSource(row.source),
        type=ItemType(row.type),
        title=row.title,
        body=row.body,
        metadata=row.metadata_json,
        created_at=row.created_at,
        updated_at=row.updated_at,
        is_deleted=row.is_deleted,
    )
