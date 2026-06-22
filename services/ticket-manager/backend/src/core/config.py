from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str
    secret_key: str
    refresh_token_secret: str
    environment: str = "development"
    log_level: str = "INFO"
    access_token_expire_minutes: int = 30
    auth_mode: str = "local"
    frontend_url: str = "http://localhost:5173"

    default_admin_email: str = ""
    default_admin_password: str = ""
    default_user_email: str = ""
    default_user_password: str = ""

    ticket_manager_service_email: str = ""

    @field_validator("secret_key", "refresh_token_secret")
    @classmethod
    def require_minimum_entropy(cls, v: str, info) -> str:
        if len(v) < 32:
            raise ValueError(
                f"{info.field_name} must be at least 32 characters; "
                'generate with: python -c "import secrets; print(secrets.token_hex(32))"'
            )
        return v


settings = Settings()  # type: ignore[call-arg]
