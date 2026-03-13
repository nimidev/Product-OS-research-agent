"""Integration framework: adapter interface and registry for API/UI layer (US-017)."""

from research_agent.integrations.adapter import (
    IntegrationAdapter,
    PrepareSyncResponse,
    TestConnectionResponse,
)
from research_agent.integrations.models import (
    EntityMappingConfig,
    IntegrationConfigRequest,
    IntegrationConfigResponse,
    entity_config_from_dict,
    entity_config_to_dict,
    response_from_db_dict,
)
from research_agent.integrations.registry import (
    IntegrationAdapterRegistry,
    get_integration_registry,
)

__all__ = [
    "EntityMappingConfig",
    "IntegrationAdapter",
    "IntegrationAdapterRegistry",
    "IntegrationConfigRequest",
    "IntegrationConfigResponse",
    "PrepareSyncResponse",
    "TestConnectionResponse",
    "entity_config_from_dict",
    "entity_config_to_dict",
    "get_integration_registry",
    "response_from_db_dict",
]
