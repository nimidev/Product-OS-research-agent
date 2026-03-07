"""Integration framework: adapter interface and registry for API/UI layer (US-017)."""

from research_agent.integrations.adapter import (
    IntegrationAdapter,
    PrepareSyncResponse,
    TestConnectionResponse,
)
from research_agent.integrations.registry import (
    IntegrationAdapterRegistry,
    get_integration_registry,
)

__all__ = [
    "IntegrationAdapter",
    "IntegrationAdapterRegistry",
    "PrepareSyncResponse",
    "TestConnectionResponse",
    "get_integration_registry",
]
