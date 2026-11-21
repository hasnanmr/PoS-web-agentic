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
    assert settings.cors_origins == ["http://localhost:5170"]


def test_reads_environment_and_normalises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "LOCAL")
    monkeypatch.setenv("LOG_LEVEL", "debug")
    monkeypatch.setenv("CORS_ORIGINS", "http://localhost:5170, https://admin.example.com ,")
    monkeypatch.setenv("DATABASE_URL", "postgresql://pos@localhost:5432/pos")
    monkeypatch.setenv("SUPABASE_URL", "")  # empty means unset
    settings = load_settings()
    assert settings.app_env == "local"
    assert settings.log_level == "DEBUG"
    assert settings.cors_origins == ["http://localhost:5170", "https://admin.example.com"]
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
    ):
        assert name in message
    assert "RABBITMQ_URL" not in message  # optional until the WhatsApp worker exists


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
        ("CORS_ORIGINS", "localhost:5170", "must start with http"),
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


def test_deployed_env_requires_a_valid_encryption_key(monkeypatch: pytest.MonkeyPatch) -> None:
    for key, value in {**DEPLOYED_ENV, "APP_ENV": "demo"}.items():
        monkeypatch.setenv(key, value)
    monkeypatch.delenv("DATA_ENCRYPTION_KEY")
    with pytest.raises(ConfigError, match="DATA_ENCRYPTION_KEY"):
        load_settings()
    monkeypatch.setenv("DATA_ENCRYPTION_KEY", "too-short")
    with pytest.raises(ConfigError, match="DATA_ENCRYPTION_KEY"):
        load_settings()
    assert load_settings(data_encryption_key=None, app_env="local").data_encryption_key is None


def test_agent_is_off_without_its_variables() -> None:
    settings = load_settings()
    assert settings.agent_configured is False
    assert settings.openai_base_url is None and settings.model_name is None


def test_agent_variables_are_read_and_the_key_stays_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_BASE_URL", "https://openrouter.ai/api/v1")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-123")
    monkeypatch.setenv("MODEL_NAME", "openai/gpt-4o-mini")
    settings = load_settings()
    assert settings.agent_configured is True
    assert str(settings.openai_base_url) == "https://openrouter.ai/api/v1"
    assert settings.model_name == "openai/gpt-4o-mini"
    assert "sk-test-123" not in repr(settings)


def test_partial_agent_config_never_blocks_the_boot(monkeypatch: pytest.MonkeyPatch) -> None:
    for key, value in {**DEPLOYED_ENV, "APP_ENV": "demo"}.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-shared-for-another-tool")
    monkeypatch.setenv("MODEL_NAME", "")  # empty counts as unset
    settings = load_settings()
    assert settings.agent_configured is False
    assert settings.agent_config_warning == (
        "web chat agent is off: OPENAI_BASE_URL, MODEL_NAME not set (buttons only)"
    )


def test_agent_without_a_key_for_self_hosted_servers(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_BASE_URL", "http://ollama:11434/v1")
    monkeypatch.setenv("MODEL_NAME", "llama3.1")
    settings = load_settings()
    assert settings.agent_configured is True and settings.openai_api_key is None
    assert settings.agent_config_warning is None


def test_agent_values_are_trimmed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_BASE_URL", " https://api.openai.com/v1 ")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-abc\n")
    monkeypatch.setenv("MODEL_NAME", "gpt-4o-mini ")
    settings = load_settings()
    assert settings.openai_api_key is not None
    assert settings.openai_api_key.get_secret_value() == "sk-abc"
    assert settings.model_name == "gpt-4o-mini"


def test_nothing_set_means_no_warning() -> None:
    assert load_settings().agent_config_warning is None
