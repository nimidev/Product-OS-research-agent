"""Configuration system — loads from config.yaml with env var resolution, falls back to .env."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field, field_validator, model_validator
from pydantic_settings import BaseSettings

load_dotenv()

CONFIG_PATH = Path(__file__).resolve().parent.parent.parent / "config.yaml"


class EmbeddingConfig(BaseModel):
    provider: str = "openai"
    model: str = "text-embedding-3-small"
    batch_size: int = 2048


class QdrantConfig(BaseModel):
    host: str = "localhost"
    port: int = 6333
    collection: str = "research_items"
    mode: str = "local"  # "local" (file-based, no Docker) or "server"
    local_path: str = "./qdrant_data"


class LLMConfig(BaseModel):
    provider: str = "openai"
    model: str = "gpt-4o"
    temperature: float = 0.3
    max_tokens: int = 1500


class LoggingConfig(BaseModel):
    level: str = "INFO"
    format: str = "json"

    @field_validator("level")
    @classmethod
    def validate_level(cls, v: str) -> str:
        valid = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if v.upper() not in valid:
            raise ValueError(f"Invalid log level: {v}. Must be one of {valid}")
        return v.upper()


class ConnectorConfig(BaseModel):
    enabled: bool = False
    extra: dict[str, Any] = Field(default_factory=dict)


class AppConfig(BaseModel):
    embedding: EmbeddingConfig = Field(default_factory=EmbeddingConfig)
    qdrant: QdrantConfig = Field(default_factory=QdrantConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    database_path: str = "research_agent.db"
    connectors: dict[str, ConnectorConfig] = Field(default_factory=dict)


def _resolve_env_vars(data: Any) -> Any:
    """Recursively resolve ${ENV_VAR} references in config values."""
    if isinstance(data, str) and data.startswith("${") and data.endswith("}"):
        env_key = data[2:-1]
        return os.environ.get(env_key, "")
    if isinstance(data, dict):
        return {k: _resolve_env_vars(v) for k, v in data.items()}
    if isinstance(data, list):
        return [_resolve_env_vars(v) for v in data]
    return data


def load_config(config_path: Path | None = None) -> AppConfig:
    """Load config from YAML file with env var resolution. Falls back to defaults."""
    path = config_path or CONFIG_PATH
    if path.exists():
        with open(path) as f:
            raw = yaml.safe_load(f) or {}
        resolved = _resolve_env_vars(raw)
        return AppConfig(**resolved)
    return AppConfig()


class Settings(BaseSettings):
    """Flat env-based settings for backward compat & quick Phase 1 usage."""

    openai_api_key: str = Field(default="")
    qdrant_host: str = Field(default="localhost")
    qdrant_port: int = Field(default=6333)
    qdrant_mode: str = Field(default="local")
    qdrant_local_path: str = Field(default="./qdrant_data")
    llm_model: str = Field(default="gpt-4o")
    embedding_model: str = Field(default="text-embedding-3-small")
    database_path: str = Field(default="research_agent.db")
    log_level: str = Field(default="INFO")

    # Jira OAuth 2.0 (3LO) — required for "Connect with Jira" flow
    jira_oauth_client_id: str = Field(default="")
    jira_oauth_client_secret: str = Field(default="")
    # Callback URL as registered in Atlassian app (e.g. http://localhost:8000/integrations/jira/oauth/callback)
    jira_oauth_redirect_uri: str = Field(default="http://localhost:8000/integrations/jira/oauth/callback")
    # Where to send user after successful OAuth (UI origin, e.g. http://localhost:3000)
    jira_oauth_frontend_origin: str = Field(default="http://localhost:3000")
    # Debug: use env credentials for token exchange when both DB and env have creds (proves DB vs env)
    jira_debug_use_env_for_token: bool = Field(default=False)

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",  # ignore JIRA_CLIENT_ID / JIRA_SECRET etc.; validator reads them from os.environ
    }

    @model_validator(mode="after")
    def _jira_env_aliases(self) -> "Settings":
        """Allow JIRA_CLIENT_ID / JIRA_SECRET as aliases if JIRA_OAUTH_* are not set."""
        if not (self.jira_oauth_client_id or "").strip():
            self.jira_oauth_client_id = (os.environ.get("JIRA_CLIENT_ID") or "").strip()
        if not (self.jira_oauth_client_secret or "").strip():
            self.jira_oauth_client_secret = (os.environ.get("JIRA_SECRET") or "").strip()
        if not self.jira_debug_use_env_for_token and os.environ.get("JIRA_DEBUG_USE_ENV") in ("1", "true", "yes"):
            self.jira_debug_use_env_for_token = True
        return self


def get_settings() -> Settings:
    return Settings()


def create_vector_store(settings: Settings | None = None) -> "QdrantStore":
    """Create a QdrantStore using the correct backend based on settings."""
    from research_agent.vector.qdrant_client import QdrantStore

    if settings is None:
        settings = get_settings()
    if settings.qdrant_mode == "local":
        return QdrantStore(path=settings.qdrant_local_path)
    return QdrantStore(host=settings.qdrant_host, port=settings.qdrant_port)
