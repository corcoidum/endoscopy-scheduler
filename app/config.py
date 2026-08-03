from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


# 개발 기본값과 .env.example의 자리표시자입니다. 운영에서 이 값이 남아 있으면 세션 서명 키나
# 초기 관리자 비밀번호가 공개된 값이라는 뜻이므로, 조용히 취약해지는 대신 시작을 거부합니다.
DEVELOPMENT_PLACEHOLDERS = {
    "secret_key": {"dev-only-change-me", "change-this-long-random-secret-before-use"},
    "initial_admin_password": {"ChangeMe!2026"},
}
MIN_PRODUCTION_SECRET_LENGTH = 32
NON_PRODUCTION_ENVIRONMENTS = {"development", "dev", "local", "test", "testing"}


class Settings(BaseSettings):
    """환경변수를 한 곳에서 읽어 앱 전체가 같은 설정을 쓰게 합니다."""

    app_name: str = "Changnyeong Endoscopy Scheduler"
    environment: str = "development"
    database_url: str = "sqlite:///./endoscopy_dev.db"
    secret_key: str = "dev-only-change-me"
    session_minutes: int = 30
    initial_admin_username: str = "admin"
    initial_admin_password: str = "ChangeMe!2026"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @property
    def is_production(self) -> bool:
        return self.environment.strip().lower() not in NON_PRODUCTION_ENVIRONMENTS

    @model_validator(mode="after")
    def reject_development_defaults_in_production(self) -> "Settings":
        if not self.is_production:
            return self

        problems: list[str] = []
        for field_name, placeholders in DEVELOPMENT_PLACEHOLDERS.items():
            if getattr(self, field_name) in placeholders:
                problems.append(f"{field_name.upper()}가 기본값입니다. .env에서 실제 값으로 바꾸세요.")
        if self.secret_key not in DEVELOPMENT_PLACEHOLDERS["secret_key"] and len(self.secret_key) < MIN_PRODUCTION_SECRET_LENGTH:
            problems.append(
                f"SECRET_KEY가 너무 짧습니다({len(self.secret_key)}자). {MIN_PRODUCTION_SECRET_LENGTH}자 이상 무작위 값을 쓰세요. "
                '생성: python -c "import secrets; print(secrets.token_urlsafe(48))"'
            )
        if problems:
            raise ValueError(f"ENVIRONMENT={self.environment} 에서 앱을 시작할 수 없습니다.\n- " + "\n- ".join(problems))
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
