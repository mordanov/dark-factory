"""Agent Dispatcher service configuration."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # App
    app_name: str = "Dark Factory Agent Dispatcher"
    environment: str = "development"
    debug: bool = False

    # PostgreSQL
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/df_dispatcher"

    # --- Keycloak / Auth ---
    keycloak_base_url: str = "http://keycloak:8080"
    keycloak_realm: str = "dark-factory"
    keycloak_client_id: str = ""
    keycloak_client_secret: str = ""
    auth_mode: str = "keycloak"
    test_jwt_secret: str = "test-secret-do-not-use-in-production"

    # Agent runner
    agent_runner_mode: str = "claude_code"  # 'claude_code' | 'api'
    claude_code_path: str = "claude"
    claude_mcp_config_path: str = "~/.claude/mcp_config.json"
    agent_prompts_dir: str = "prompts"

    # Timeouts
    agent_timeout_default: int = 300

    # Worker
    worker_max_concurrent_runs: int = 3
    poll_interval_seconds: int = 10

    # Brainstorm
    brainstorm_agents: str = "software-architect,security-architect"
    brainstorm_max_rounds: int = 3

    # Agent registry
    agent_registry_path: str = ""  # override path; empty = use resolved_registry_path

    # Context
    context_max_tokens: int = 4000

    # Upstream services
    orchestrator_base_url: str = "http://orchestrator:8000"
    ticket_manager_base_url: str = "http://ticket-manager:8000"
    context_distiller_base_url: str = "http://context-distiller:8000"

    # OpenAI
    openai_api_key: str = ""
    openai_model: str = "gpt-4o"
    openai_base_url: str | None = None  # override for Azure / local proxy

    # CORS
    cors_allow_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])

    def agent_timeout_for(self, agent_id: str) -> int:
        """Return per-agent timeout or fall back to default."""
        env_key = f"AGENT_TIMEOUT_{agent_id.upper()}"
        raw = os.environ.get(env_key)
        if raw is not None:
            try:
                return int(raw)
            except ValueError:
                pass
        return self.agent_timeout_default

    @property
    def resolved_registry_path(self) -> str:
        if self.agent_registry_path:
            return self.agent_registry_path
        return str(Path(self.agent_prompts_dir).parent / "registry.yaml")

    @property
    def brainstorm_agents_list(self) -> list[str]:
        from src.core.constants import VALID_AGENT_IDS

        agents = [a.strip() for a in self.brainstorm_agents.split(",") if a.strip()]
        invalid = [a for a in agents if a not in VALID_AGENT_IDS]
        if invalid:
            raise ValueError(f"BRAINSTORM_AGENTS contains unknown agent IDs: {invalid}")
        return agents


@lru_cache
def get_settings() -> Settings:
    return Settings()
