from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/df_ticket_manager"
    environment: str = "development"
    log_level: str = "INFO"
    frontend_url: str = "http://localhost:5173"

    # --- Keycloak / Auth ---
    keycloak_base_url: str = "http://keycloak:8080"
    keycloak_realm: str = "dark-factory"
    keycloak_client_id: str = ""
    keycloak_client_secret: str = ""
    auth_mode: str = "keycloak"
    test_jwt_secret: str = "test-secret-do-not-use-in-production"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
