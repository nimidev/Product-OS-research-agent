"""Registry of integration adapters by source_id (US-017)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from research_agent.integrations.adapter import IntegrationAdapter


class IntegrationAdapterRegistry:
    """
    Registry of integration adapters by source_id.

    Allows the API to dispatch by source_id and the UI to discover
    available integrations and their auth type without hardcoding.
    """

    def __init__(self) -> None:
        self._adapters: dict[str, IntegrationAdapter] = {}
        self._auth_types: dict[str, str] = {}

    def register(
        self,
        source_id: str,
        adapter: IntegrationAdapter,
        *,
        auth_type: str | None = None,
    ) -> None:
        """Register an adapter for the given source_id."""
        self._adapters[source_id] = adapter
        self._auth_types[source_id] = auth_type if auth_type is not None else adapter.auth_type

    def get(self, source_id: str) -> IntegrationAdapter | None:
        """Return the adapter for source_id, or None if not registered."""
        return self._adapters.get(source_id)

    def list_integrations(self) -> list[dict[str, Any]]:
        """
        Return list of registered integrations for UI discoverability.
        Each item has source_id and auth_type (e.g. "api_key", "oauth").
        """
        return [
            {"source_id": sid, "auth_type": self._auth_types.get(sid, "api_key")}
            for sid in self._adapters
        ]

    def source_ids(self) -> list[str]:
        """Return registered source_ids."""
        return list(self._adapters.keys())


# Global registry instance. Populated when adapters are implemented (Tasks 4–5).
# API can use: from research_agent.integrations.registry import get_integration_registry
_default_registry: IntegrationAdapterRegistry | None = None


def get_integration_registry() -> IntegrationAdapterRegistry:
    """Return the default integration adapter registry (singleton)."""
    global _default_registry
    if _default_registry is None:
        _default_registry = IntegrationAdapterRegistry()
    return _default_registry
