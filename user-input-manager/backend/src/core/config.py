"""Application configuration.

All runtime configuration comes from environment variables so the same
container image works in dev/test/prod (12-factor style). Centralising it
here keeps every other module free of `os.environ` calls (DRY).
"""
from __future__ import annotations

from functools import lru_cache
from typing import List

from pydantic import AnyHttpUrl, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- App ---
    app_name: str = "Dark Factory Prompt Studio"
    environment: str = Field(default="development")
    debug: bool = Field(default=False)

    # --- Database ---
    database_url: str = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/dark_factory",
        description="SQLAlchemy async database URL.",
    )

    # --- JWT / Auth ---
    jwt_secret_key: str = Field(default="CHANGE_ME_INSECURE_DEFAULT")
    jwt_algorithm: str = Field(default="HS256")
    access_token_expires_minutes: int = Field(default=30)
    refresh_token_expires_days: int = Field(default=7)

    # --- Initial admin seed ---
    initial_admin_email: str = Field(default="admin@dark-factory.local")
    initial_admin_password: str = Field(default="ChangeMe123!")

    # --- CORS ---
    cors_allow_origins: List[str] = Field(default_factory=lambda: ["http://localhost:5173"])

    # --- OpenAI ---
    openai_api_key: str = Field(default="")
    openai_model: str = Field(default="gpt-4o-mini")
    openai_base_url: str | None = Field(default=None)
    openai_timeout_seconds: float = Field(default=60.0)

    # --- Orchestrator Service ---
    orchestrator_base_url: str = Field(default="http://orchestrator:8000")
    orchestrator_timeout_seconds: float = Field(default=60.0)

    # --- Ticket Manager integration ---
    ticket_manager_base_url: AnyHttpUrl = Field(
        default="https://ticket-manager.dark-factory.miveralta.ru"
    )
    ticket_manager_service_email: str = Field(default="")
    ticket_manager_service_password: str = Field(default="")
    ticket_manager_timeout_seconds: float = Field(default=20.0)
    ticket_manager_context_max_tickets: int = Field(default=50)
    ticket_manager_context_max_chars: int = Field(default=6000)

    @field_validator("cors_allow_origins", mode="before")
    @classmethod
    def _split_csv(cls, value):
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value


@lru_cache
def get_settings() -> Settings:
    """Cached settings accessor (Settings is immutable for the process lifetime)."""

    return Settings()
