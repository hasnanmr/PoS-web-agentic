from __future__ import annotations

import pytest

from app.config import Settings

ENV_VARS = (
    "APP_ENV",
    "PORT",
    "LOG_LEVEL",
    "DATABASE_URL",
    "SUPABASE_URL",
    "SUPABASE_JWKS_URL",
    "SUPABASE_JWT_ISSUER",
    "RABBITMQ_URL",
    "DEFAULT_TIMEZONE",
    "CORS_ORIGINS",
    "SUPABASE_JWT_AUDIENCE",
    "JWT_ALGORITHMS",
    "JWKS_CACHE_SECONDS",
    "SUPABASE_SERVICE_ROLE_KEY",
    "DB_POOL_MIN_SIZE",
    "DB_POOL_MAX_SIZE",
    "ADMIN_APP_URL",
    "WHATSAPP_APP_SECRET",
    "WHATSAPP_VERIFY_TOKEN",
    "WHATSAPP_ACCESS_TOKEN",
    "WHATSAPP_GRAPH_URL",
    "WHATSAPP_GRAPH_VERSION",
)

DEPLOYED_ENV = {
    "DATABASE_URL": "postgresql://user:pass@db.example.com:5432/postgres",
    "SUPABASE_URL": "https://abc.supabase.co",
    "SUPABASE_JWKS_URL": "https://abc.supabase.co/auth/v1/.well-known/jwks.json",
    "SUPABASE_JWT_ISSUER": "https://abc.supabase.co/auth/v1",
    "RABBITMQ_URL": "amqps://user:pass@mq.example.com/vhost",
    "CORS_ORIGINS": "https://admin.example.com",
}


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Isolate tests from the developer's shell and any backend/.env file."""
    for name in ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setitem(Settings.model_config, "env_file", None)
