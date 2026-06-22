"""ContextDistiller configuration."""

from __future__ import annotations

from functools import lru_cache

from pydantic import AnyHttpUrl, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Dark Factory ContextDistiller"
    environment: str = "development"
    debug: bool = False

    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/df_orchestrator"

    mongo_url: str = "mongodb://mongo:27017"
    mongo_db_name: str = "dark_factory_docs"

    jwt_secret_key: str = Field(default="CHANGE_ME")
    jwt_algorithm: str = "HS256"
    auth_mode: str = "local"

    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    openai_timeout_seconds: float = 120.0

    ticket_manager_base_url: AnyHttpUrl = Field(default="http://ticket-manager:8000")
    ticket_manager_service_email: str = ""
    ticket_manager_service_password: str = ""

    distiller_max_memory_tokens: int = 2000
    distiller_memory_history_keep: int = 20

    worker_max_concurrent_jobs: int = Field(default=3)
    worker_poll_interval_seconds: int = Field(default=5)


@lru_cache
def get_settings() -> Settings:
    return Settings()
