"""Configuration system — loads from config.yaml with env var resolution, falls back to .env."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field, field_validator
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


class LLMConfig(BaseModel):
    provider: str = "openai"
    model: str = "gpt-4o-mini"
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
    llm_model: str = Field(default="gpt-4o-mini")
    embedding_model: str = Field(default="text-embedding-3-small")
    database_path: str = Field(default="research_agent.db")
    log_level: str = Field(default="INFO")

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


def get_settings() -> Settings:
    return Settings()
