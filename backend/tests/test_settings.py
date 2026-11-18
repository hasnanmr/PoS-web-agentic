from __future__ import annotations

import pytest

from app.config import ConfigError, load_settings
from tests.conftest import DEPLOYED_ENV


def test_local_defaults() -> None:
    settings = load_settings()
    assert settings.app_env == "local"
    assert settings.default_timezone == "Asia/Jakarta"
    assert settings.timezone.key == "Asia/Jakarta"
    assert settings.database_url is None
    assert settings.log_level == "INFO"
    assert settings.cors_origins == ["http://localhost:5173"]


def test_reads_environment_and_normalises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "LOCAL")
    monkeypatch.setenv("LOG_LEVEL", "debug")
    monkeypatch.setenv("CORS_ORIGINS", "http://localhost:5173, https://admin.example.com ,")
    monkeypatch.setenv("DATABASE_URL", "postgresql://pos:pos@localhost:5432/pos")
    monkeypatch.setenv("SUPABASE_URL", "")  # empty means unset
    settings = load_settings()
    assert settings.app_env == "local"
    assert settings.log_level == "DEBUG"
    assert settings.cors_origins == ["http://localhost:5173", "https://admin.example.com"]
    assert str(settings.database_url).startswith("postgresql://")
    assert settings.supabase_url is None


@pytest.mark.parametrize("app_env", ["demo", "staging", "production"])
def test_deployed_envs_require_infrastructure_vars(
    monkeypatch: pytest.MonkeyPatch, app_env: str
) -> None:
    monkeypatch.setenv("APP_ENV", app_env)
    with pytest.raises(ConfigError) as excinfo:
        load_settings()
    message = str(excinfo.value)
    for name in (
        "DATABASE_URL",
        "SUPABASE_URL",
        "SUPABASE_JWKS_URL",
        "SUPABASE_JWT_ISSUER",
        "RABBITMQ_URL",
    ):
        assert name in message


@pytest.mark.parametrize("app_env", ["demo", "staging", "production"])
def test_deployed_envs_accept_complete_config(
    monkeypatch: pytest.MonkeyPatch, app_env: str
) -> None:
    monkeypatch.setenv("APP_ENV", app_env)
    for key, value in DEPLOYED_ENV.items():
        monkeypatch.setenv(key, value)
    settings = load_settings()
    assert settings.app_env == app_env


def test_deployed_env_rejects_wildcard_cors(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    for key, value in DEPLOYED_ENV.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("CORS_ORIGINS", "*")
    with pytest.raises(ConfigError, match="CORS_ORIGINS"):
        load_settings()


@pytest.mark.parametrize(
    ("name", "value", "expected"),
    [
        ("APP_ENV", "prod", "APP_ENV"),
        ("LOG_LEVEL", "verbose", "LOG_LEVEL"),
        ("DEFAULT_TIMEZONE", "Mars/Olympus", "unknown IANA time zone"),
        ("DATABASE_URL", "mysql://x@localhost/db", "DATABASE_URL"),
        ("RABBITMQ_URL", "http://mq.example.com", "RABBITMQ_URL"),
        ("SUPABASE_URL", "not-a-url", "SUPABASE_URL"),
        ("CORS_ORIGINS", "localhost:5173", "must start with http"),
        ("PORT", "0", "PORT"),
    ],
)
def test_invalid_values_fail_fast(
    monkeypatch: pytest.MonkeyPatch, name: str, value: str, expected: str
) -> None:
    monkeypatch.setenv(name, value)
    with pytest.raises(ConfigError) as excinfo:
        load_settings()
    assert "Invalid configuration" in str(excinfo.value)
    assert expected in str(excinfo.value)
