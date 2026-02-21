"""Abstract base connector — contract for all data source integrations."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any

from research_agent.storage.models import Entity


class BaseConnector(ABC):
    """Contract for data source connectors.

    Connectors fetch raw items and normalize to Entity (with entity_fields)
    using config-driven field_mappings. Each connector instance typically
    represents one source + entity_type (e.g. one Monday board for feature_request).
    """

    @property
    @abstractmethod
    def source_name(self) -> str:
        """Unique identifier for this data source (e.g. 'monday', 'notion')."""

    @property
    @abstractmethod
    def entity_type(self) -> str:
        """Canonical entity type this connector produces (e.g. 'feature_request')."""

    @abstractmethod
    async def list_updated_items(self, since: datetime | None = None) -> list[Entity]:
        """Fetch items updated since the given timestamp, normalized to Entity.

        If since is None, fetch all items (initial sync).
        """

    @abstractmethod
    def normalize_item(self, raw: Any) -> Entity:
        """Transform a raw API response item into an Entity with fields."""

    async def health_check(self) -> bool:
        """Verify connectivity to the data source. Override for real connectors."""
        return True
