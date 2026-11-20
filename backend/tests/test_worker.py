from __future__ import annotations

import asyncio

import pytest

from app.config import Settings, get_settings
from app.worker import main as worker


@pytest.fixture(autouse=True)
def reset_settings_cache() -> None:
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_worker_refuses_to_start_without_its_variables(capsys: pytest.CaptureFixture[str]) -> None:
    assert worker.main() == 1
    err = capsys.readouterr().err
    assert "DATABASE_URL" in err and "RABBITMQ_URL" in err and "WHATSAPP_ACCESS_TOKEN" in err


def test_worker_fails_fast_on_invalid_config(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    assert worker.main() == 1
    assert "requires these variables" in capsys.readouterr().err


def test_worker_runs_with_a_complete_config(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://app_backend@localhost:5432/pos")
    monkeypatch.setenv("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/")
    monkeypatch.setenv("WHATSAPP_ACCESS_TOKEN", "token")
    started: list[Settings] = []

    async def fake_run(settings: Settings, stop: asyncio.Event) -> None:
        started.append(settings)

    monkeypatch.setattr(worker, "run", fake_run)
    assert worker.main() == 0
    assert started and started[0].whatsapp_access_token is not None
