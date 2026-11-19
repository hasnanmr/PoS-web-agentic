"""Menu photo checks (T-132) and O11 change text (T-101), without a database."""

from __future__ import annotations

from uuid import UUID

import pytest

from app.core.audit_log import change_text
from app.core.catalog import photo_object_path, validate_photo
from app.core.errors import ValidationFailedError

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 8
JPG = b"\xff\xd8\xff\xe0" + b"\x00" * 8
WEBP = b"RIFF\x00\x00\x00\x00WEBPVP8 "


def test_validate_photo_checks_signature_and_size() -> None:
    assert validate_photo("image/png", PNG) == "image/png"
    assert validate_photo("image/jpg; charset=binary", JPG) == "image/jpeg"
    assert validate_photo("IMAGE/WEBP", WEBP) == "image/webp"
    for kind, data in (("image/png", JPG), ("image/gif", b"GIF89a"), ("", PNG)):
        with pytest.raises(ValidationFailedError):
            validate_photo(kind, data)
    with pytest.raises(ValidationFailedError, match="5 MB"):
        validate_photo("image/png", PNG + b"\x00" * (5 * 1024 * 1024))


def test_photo_object_path_is_new_each_time() -> None:
    t, p = UUID(int=1), UUID(int=2)
    a, b = photo_object_path(t, p, "image/webp"), photo_object_path(t, p, "image/webp")
    assert a != b and a.startswith(f"{t}/{p}/") and a.endswith(".webp")


def _row(event: str, **kw: object) -> dict[str, object]:
    base = {"from_status": None, "to_status": None, "from_payment": None, "to_payment": None}
    return {**base, "event": event, "data": kw.pop("data", {}), **kw}


def test_change_text_matches_the_wireframe() -> None:
    assert change_text(_row("status_changed", from_status="preparing", to_status="ready")) == (
        "preparing → ready"
    )
    assert change_text(_row("reversed", from_payment="paid", to_payment="refunded")) == (
        "paid → refunded"
    )
    rev = _row(
        "reversed", from_payment="paid", to_payment="refunded", data={"ingredients": "waste"}
    )
    assert change_text(rev) == "paid → refunded · bahan → waste"
    assert change_text(_row("proof_rejected")) == "proof rejected"
    paid = _row(
        "payment_changed", from_payment="unpaid", to_payment="paid", data={"method": "qris"}
    )
    assert change_text(paid) == "marked paid (QRIS)"
    assert change_text(_row("payment_changed", from_payment="unpaid", to_payment="paid")) == (
        "unpaid → paid"
    )
