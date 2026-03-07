"""Integration adapter interface — API/UI contract for all integrations (US-017)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel

if TYPE_CHECKING:
    from research_agent.storage.db import Database


class TestConnectionResponse(BaseModel):
    """Response from test_connection; used by all adapters."""

    ok: bool
    detail: str = ""


class PrepareSyncResponse(BaseModel):
    """Response from prepare_sync; used by all adapters."""

    ok: bool
    detail: str = ""
    fetched: int = 0
    embedded: int = 0
    errors: int = 0
    total_entities: int = 0


AuthType = Literal["oauth", "api_key"]


class IntegrationAdapter(ABC):
    """
    Contract for the API/UI layer of an integration.

    Adapters handle config CRUD, schema discovery, test_connection, and prepare_sync.
    Sync/ingestion is handled by BaseConnector (see connectors/base.py).
    """

    @property
    @abstractmethod
    def source_id(self) -> str:
        """Unique identifier for this integration (e.g. 'monday', 'jira')."""

    @property
    @abstractmethod
    def auth_type(self) -> AuthType:
        """Auth type so the UI can render the correct auth step (API key form vs OAuth)."""

    @abstractmethod
    async def get_config(self, db: Database) -> dict[str, Any]:
        """
        Return current config for this integration.
        No raw secrets in response; use *_set booleans (e.g. api_key_set).
        """
        ...

    @abstractmethod
    async def upsert_config(
        self,
        db: Database,
        request: dict[str, Any],
    ) -> dict[str, Any]:
        """Persist config (credentials, entity mappings, scope).
        Returns same shape as get_config.
        """
        ...

    @abstractmethod
    async def get_schema(self, db: Database) -> dict[str, Any]:
        """
        Return list of source entities (e.g. boards, projects) and their fields for mapping.
        Shape: e.g. { "scopes": [...], "fields_by_scope": {...} } or provider-specific.
        """
        ...

    @abstractmethod
    async def test_connection(self, db: Database) -> TestConnectionResponse:
        """Verify credentials and connectivity."""
        ...

    @abstractmethod
    async def prepare_sync(self, db: Database) -> PrepareSyncResponse:
        """Run a one-off sync/prepare for the configured scope (fetch, normalize, embed)."""
        ...

    # Optional OAuth hooks — override only for OAuth-based integrations.
    def get_oauth_authorize_url(
        self,
        state: str,
        redirect_uri: str,
    ) -> str:
        """Return URL to send the user to for OAuth. Override for OAuth adapters."""
        raise NotImplementedError("This integration does not use OAuth")

    async def handle_oauth_callback(
        self,
        db: Database,
        code: str,
        state: str,
        redirect_uri: str,
    ) -> None:
        """Exchange code for tokens and persist in config. Override for OAuth adapters."""
        raise NotImplementedError("This integration does not use OAuth")
