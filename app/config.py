from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """환경변수를 한 곳에서 읽어 앱 전체가 같은 설정을 쓰게 합니다."""

    app_name: str = "Changnyeong Endoscopy Scheduler"
    environment: str = "development"
    database_url: str = "sqlite:///./endoscopy_dev.db"
    secret_key: str = "dev-only-change-me"
    session_minutes: int = 30
    initial_admin_username: str = "admin"
    initial_admin_password: str = "ChangeMe!2026"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


@lru_cache
def get_settings() -> Settings:
    return Settings()

