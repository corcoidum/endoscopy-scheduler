"""운영 배포에서 기본 비밀값과 평문 세션 쿠키가 남지 않도록 강제하는 테스트."""

import pytest
from pydantic import ValidationError

from app.config import Settings
from app.routers import auth as auth_router


PRODUCTION_SECRET = "s" * 48


def production_settings(**overrides) -> Settings:
    values = {
        "environment": "production",
        "secret_key": PRODUCTION_SECRET,
        "initial_admin_password": "RealDeployPassword!2026",
    }
    values.update(overrides)
    return Settings(**values)


def test_production_rejects_default_secret_key():
    with pytest.raises(ValidationError) as error:
        production_settings(secret_key="dev-only-change-me")

    assert "SECRET_KEY" in str(error.value)


def test_production_rejects_env_example_placeholder_secret():
    with pytest.raises(ValidationError):
        production_settings(secret_key="change-this-long-random-secret-before-use")


def test_production_rejects_short_secret_key():
    with pytest.raises(ValidationError) as error:
        production_settings(secret_key="tooshort")

    assert "짧습니다" in str(error.value)


def test_production_rejects_default_initial_admin_password():
    with pytest.raises(ValidationError) as error:
        production_settings(initial_admin_password="ChangeMe!2026")

    assert "INITIAL_ADMIN_PASSWORD" in str(error.value)


def test_production_accepts_configured_secrets():
    settings = production_settings()

    assert settings.is_production is True


def test_development_keeps_defaults_usable():
    # 로컬 .env 값에 영향받지 않도록 개발 기본값을 명시적으로 넣어 검증합니다.
    settings = Settings(
        environment="development",
        secret_key="dev-only-change-me",
        initial_admin_password="ChangeMe!2026",
    )

    assert settings.is_production is False
    assert settings.secret_key == "dev-only-change-me"


def test_session_cookie_is_not_secure_in_development(client):
    response = client.post("/login", data={"username": "staff", "password": "Password!123"}, follow_redirects=False)

    assert response.status_code == 303
    assert "secure" not in response.headers["set-cookie"].lower()


def test_session_cookie_is_secure_in_production(client, monkeypatch):
    monkeypatch.setattr(auth_router, "get_settings", production_settings)

    response = client.post("/login", data={"username": "staff", "password": "Password!123"}, follow_redirects=False)

    assert response.status_code == 303
    cookie = response.headers["set-cookie"].lower()
    assert "secure" in cookie
    assert "httponly" in cookie
    assert "samesite=strict" in cookie
