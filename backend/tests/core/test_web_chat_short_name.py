"""C1 header avatar initials (app.core.web_chat.short_name)."""

from app.core.web_chat import short_name


def test_initials_skip_punctuation_words() -> None:
    assert short_name("Kopi Senja – Dago") == "KS"  # noqa: RUF001 - outlet names use an en dash
    assert short_name("Bandung – Dago") == "BD"  # noqa: RUF001
    assert short_name("  ") == "?"
