"""Langfuse tracing (opt-in): off without keys, and personal data masked before export."""

from __future__ import annotations

from app.config import load_settings
from app.core.agent import tracing


def test_off_without_both_keys(monkeypatch) -> None:
    assert tracing.configure(load_settings()) is False
    assert tracing.enabled() is False and tracing.new_trace_id() is None
    assert (
        tracing.run_config(
            trace_id="t", session="a" * 64, outlet_id="o", context="order", prompt_version="v"
        )
        == {}
    )
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-lf-test")
    settings = load_settings()
    assert settings.langfuse_configured is False  # a secret key is needed too
    assert settings.langfuse_host is None  # tracing then uses tracing.DEFAULT_HOST
    monkeypatch.setenv("LANGFUSE_HOST", "")
    assert load_settings().langfuse_host is None  # an empty line in .env is "not set"


def test_keys_are_read_and_the_secret_stays_hidden(monkeypatch) -> None:
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", " pk-lf-test ")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-lf-secret\n")
    monkeypatch.setenv("LANGFUSE_HOST", "https://langfuse.internal.example")
    settings = load_settings()
    assert settings.langfuse_configured is True
    assert settings.langfuse_public_key == "pk-lf-test"
    assert "sk-lf-secret" not in repr(settings)


def test_phone_numbers_and_emails_are_masked_everywhere() -> None:
    data = {
        "input": [{"content": "atas nama Rina 0812-3456-7221, email rina.s@mail.co.id"}],
        "output": "Siap kak, +62 812 3456 7221 sudah dicatat",
        "n": 3,
        "nested": ("08123456789",),
    }
    masked = tracing.mask(data=data)
    text = str(masked)
    assert "3456" not in text and "rina.s@" not in text
    assert "[no HP]" in text and "[email]" in text
    assert masked["n"] == 3
    # Prices and times are not phone numbers.
    assert (
        tracing.mask(data="Total Rp 92.400, jam 19:00, 2 orang")
        == "Total Rp 92.400, jam 19:00, 2 orang"
    )
