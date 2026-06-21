from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    git_repo_path: str
    jwt_secret_key: str
    jwt_algorithm: str = "HS256"
    distiller_base_url: str = "http://context-distiller:8001"
    distiller_timeout_seconds: int = 10
    git_read_timeout_seconds: int = 15
    search_max_results: int = 50

    def validate_repo(self) -> None:
        p = Path(self.git_repo_path)
        if not p.exists() or not (p / ".git").exists():
            raise ValueError(f"GIT_REPO_PATH '{self.git_repo_path}' is not a valid git repository")


@lru_cache
def get_settings() -> Settings:
    return Settings()
