"""Application settings loaded from environment variables (and an optional `.env`).

Validation is strict and fails fast: an invalid or incomplete configuration raises
`ConfigError` with a readable list of problems before any server or worker starts.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Annotated, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import (
    AmqpDsn,
    AnyHttpUrl,
    Field,
    PostgresDsn,
    ValidationError,
    field_validator,
    model_validator,
)
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

AppEnv = Literal["local", "demo", "staging", "production"]
LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]

# Variables that must be set in every environment except `local`.
REQUIRED_OUTSIDE_LOCAL: tuple[str, ...] = (
    "database_url",
    "supabase_url",
    "supabase_jwks_url",
    "supabase_jwt_issuer",
    "rabbitmq_url",
)


class ConfigError(RuntimeError):
    """Raised when the environment does not describe a valid configuration."""


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_env: AppEnv = "local"
    port: int = Field(default=8000, ge=1, le=65535)  # Railway injects PORT
    log_level: LogLevel = "INFO"

    database_url: PostgresDsn | None = None
    supabase_url: AnyHttpUrl | None = None
    supabase_jwks_url: AnyHttpUrl | None = None
    supabase_jwt_issuer: str | None = None
    rabbitmq_url: AmqpDsn | None = None

    default_timezone: str = "Asia/Jakarta"
    cors_origins: Annotated[list[str], NoDecode] = ["http://localhost:5173"]

    @field_validator(
        "database_url",
        "supabase_url",
        "supabase_jwks_url",
        "supabase_jwt_issuer",
        "rabbitmq_url",
        mode="before",
    )
    @classmethod
    def _empty_to_none(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("app_env", mode="before")
    @classmethod
    def _lower_env(cls, value: object) -> object:
        return value.strip().lower() if isinstance(value, str) else value

    @field_validator("log_level", mode="before")
    @classmethod
    def _upper_level(cls, value: object) -> object:
        return value.strip().upper() if isinstance(value, str) else value

    @field_validator("default_timezone")
    @classmethod
    def _valid_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError(f"unknown IANA time zone {value!r}") from exc
        return value

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @field_validator("cors_origins")
    @classmethod
    def _valid_origins(cls, value: list[str]) -> list[str]:
        for origin in value:
            if origin != "*" and not origin.startswith(("http://", "https://")):
                raise ValueError(f"CORS origin {origin!r} must start with http:// or https://")
        return value

    @model_validator(mode="after")
    def _require_in_deployed_envs(self) -> Settings:
        if self.app_env == "local":
            return self
        missing = [name.upper() for name in REQUIRED_OUTSIDE_LOCAL if getattr(self, name) is None]
        if missing:
            raise ValueError(
                f"APP_ENV={self.app_env} requires these variables: {', '.join(missing)}"
            )
        if "*" in self.cors_origins:
            raise ValueError(f"CORS_ORIGINS must not contain '*' when APP_ENV={self.app_env}")
        return self

    @property
    def timezone(self) -> ZoneInfo:
        return ZoneInfo(self.default_timezone)

    @property
    def is_local(self) -> bool:
        return self.app_env == "local"


def _format_errors(exc: ValidationError) -> str:
    lines = []
    for err in exc.errors():
        field = ".".join(str(part) for part in err["loc"]).upper()
        message = err["msg"].removeprefix("Value error, ")
        lines.append(f"  - {field}: {message}" if field else f"  - {message}")
    return "Invalid configuration:\n" + "\n".join(lines)


def load_settings(**overrides: object) -> Settings:
    """Build settings, converting validation errors into a readable `ConfigError`."""
    try:
        return Settings(**overrides)  # type: ignore[arg-type]
    except ValidationError as exc:
        raise ConfigError(_format_errors(exc)) from None


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return load_settings()
