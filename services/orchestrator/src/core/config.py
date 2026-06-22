"""Orchestrator Service configuration."""

from __future__ import annotations

from functools import lru_cache

from pydantic import AnyHttpUrl, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # App
    app_name: str = "Dark Factory Orchestrator"
    environment: str = "development"
    debug: bool = False

    # PostgreSQL (queue + audit + jobs)
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/df_orchestrator"
    database_url_sync: str = "postgresql://postgres:postgres@localhost:5432/df_orchestrator"

    # MongoDB (Document Store: project_memory + ADRs)
    mongo_url: str = "mongodb://mongo:27017"
    mongo_db_name: str = "dark_factory_docs"

    # JWT (validates tokens from Prompt Studio users)
    jwt_secret_key: str = Field(default="CHANGE_ME")
    jwt_algorithm: str = "HS256"
    auth_mode: str = "local"

    # OpenAI
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    openai_timeout_seconds: float = 120.0

    # Ticket Manager
    ticket_manager_base_url: AnyHttpUrl = Field(
        default="https://ticket-manager.dark-factory.miveralta.ru"
    )
    ticket_manager_service_email: str = ""
    ticket_manager_service_password: str = ""
    ticket_manager_timeout_seconds: float = 20.0

    # Worker
    worker_max_concurrent_tickets: int = Field(default=5)
    worker_poll_interval_seconds: int = Field(
        default=5, description="PG LISTEN fallback poll interval"
    )

    # ContextDistiller
    distiller_max_memory_tokens: int = 2000
    distiller_memory_history_keep: int = 20

    # CORS
    cors_allow_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])


@lru_cache
def get_settings() -> Settings:
    return Settings()
