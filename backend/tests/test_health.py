from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import db
from app.config import load_settings
from app.main import create_app


def make_client(**overrides: object) -> TestClient:
    return TestClient(create_app(load_settings(**overrides)))


def test_healthz() -> None:
    response = make_client().get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "env": "local", "version": "unknown"}


def test_readyz_without_database_reports_not_configured() -> None:
    response = make_client().get("/readyz")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "checks": {"database": "not_configured"},
        "version": "unknown",
    }


def test_readyz_with_reachable_database(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    async def fake_ping(url: str) -> None:
        calls.append(url)

    monkeypatch.setattr(db, "ping", fake_ping)
    client = make_client(database_url="postgresql://pos@localhost:5432/pos")
    response = client.get("/readyz")
    assert response.status_code == 200
    assert response.json()["checks"] == {"database": "ok"}
    assert calls and calls[0].startswith("postgresql://")


def test_readyz_with_unreachable_database_returns_503() -> None:
    # Port 1 on localhost refuses connections immediately.
    client = make_client(database_url="postgresql://pos@127.0.0.1:1/pos")
    response = client.get("/readyz")
    assert response.status_code == 503
    assert response.json() == {
        "status": "unavailable",
        "checks": {"database": "error"},
        "version": "unknown",
    }


def test_cors_allows_configured_origin() -> None:
    client = make_client(cors_origins=["http://localhost:5170"])
    response = client.options(
        "/healthz",
        headers={"Origin": "http://localhost:5170", "Access-Control-Request-Method": "GET"},
    )
    assert response.headers.get("access-control-allow-origin") == "http://localhost:5170"


def test_build_sha_comes_from_the_ci_stamp(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    from app import version

    stamp = tmp_path / "BUILD_SHA"
    monkeypatch.setattr(version, "_FILE", stamp)
    assert version.build_sha() == "unknown"
    stamp.write_text("d50e05d6c594b3ae33b745acd0a920ad1b874aee\n")
    assert version.build_sha() == "d50e05d6c594b3ae33b745acd0a920ad1b874aee"
