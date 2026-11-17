from __future__ import annotations

import pytest

from app.config import get_settings
from app.worker import main as worker


@pytest.fixture(autouse=True)
def reset_settings_cache() -> None:
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_worker_starts_with_valid_config(capsys: pytest.CaptureFixture[str]) -> None:
    assert worker.main() == 0
    assert "not implemented" in capsys.readouterr().out


def test_worker_fails_fast_on_invalid_config(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    assert worker.main() == 1
    assert "requires these variables" in capsys.readouterr().err
