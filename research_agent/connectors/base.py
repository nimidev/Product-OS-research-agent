"""Abstract base connector — contract for all data source integrations."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class NormalizedItem:
    """Connector-agnostic representation of a source item."""

    id: str
    source: str
    type: str
    title: str
    body: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime | None = None
    updated_at: datetime | None = None
    is_deleted: bool = False


class BaseConnector(ABC):
    """Contract for data source connectors.

    Implementing a new connector requires only:
    1. Subclass BaseConnector
    2. Implement list_updated_items and normalize_item
    3. Add config entry
    """

    @property
    @abstractmethod
    def source_name(self) -> str:
        """Unique identifier for this data source (e.g., 'monday', 'notion')."""

    @abstractmethod
    async def list_updated_items(self, since: datetime | None = None) -> list[NormalizedItem]:
        """Fetch items updated since the given timestamp.

        If since is None, fetch all items (initial sync).
        """

    @abstractmethod
    def normalize_item(self, raw: Any) -> NormalizedItem:
        """Transform a raw API response item into a NormalizedItem."""

    async def health_check(self) -> bool:
        """Verify connectivity to the data source. Override for real connectors."""
        return True
