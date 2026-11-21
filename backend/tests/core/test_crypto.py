"""Field encryption and blind indexes (app.core.crypto)."""

from __future__ import annotations

import base64

import pytest

from app.core import crypto

KEY_A = base64.b64encode(b"a" * 32).decode()
KEY_B = base64.b64encode(b"b" * 32).decode()


@pytest.fixture(autouse=True)
def _key_a() -> None:
    crypto.configure(KEY_A)
    yield
    crypto.configure(None)


def test_round_trip_and_random_nonce() -> None:
    one = crypto.encrypt("0812-3456-7890", "customers.phone")
    two = crypto.encrypt("0812-3456-7890", "customers.phone")
    assert one is not None and one.startswith("enc:v1:") and one != two
    assert "0812" not in one
    assert crypto.decrypt(one, "customers.phone") == "0812-3456-7890"
    assert crypto.encrypt(None, "x") is None and crypto.decrypt(None, "x") is None


def test_ciphertext_is_bound_to_its_column() -> None:
    value = crypto.encrypt("Rina", "customers.name")
    with pytest.raises(crypto.CryptoError):
        crypto.decrypt(value, "orders.customer_name")


def test_tampering_or_another_key_fails() -> None:
    value = crypto.encrypt("Jl. Dago 1", "orders.delivery_address")
    assert value is not None
    middle = len(value) // 2
    flipped = value[:middle] + ("A" if value[middle] != "A" else "B") + value[middle + 1 :]
    with pytest.raises(crypto.CryptoError):
        crypto.decrypt(flipped, "orders.delivery_address")
    crypto.configure(KEY_B)
    with pytest.raises(crypto.CryptoError):
        crypto.decrypt(value, "orders.delivery_address")


def test_legacy_plaintext_is_returned_as_is() -> None:
    assert crypto.decrypt("Rina", "orders.customer_name") == "Rina"
    assert not crypto.is_encrypted("Rina")


def test_blind_index_is_keyed_and_per_context() -> None:
    a = crypto.blind_index("081234567890", "phone")
    assert a == crypto.blind_index("081234567890", "phone") and len(a) == 64
    assert a != crypto.blind_index("081234567890", "booking_code")
    crypto.configure(KEY_B)
    assert a != crypto.blind_index("081234567890", "phone")  # useless without the key


def test_sha256_hex() -> None:
    assert crypto.sha256_hex("abc") == (
        "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    )


@pytest.mark.parametrize("bad", ["not base64!!", base64.b64encode(b"short").decode()])
def test_key_must_be_32_bytes_of_base64(bad: str) -> None:
    with pytest.raises(ValueError, match="DATA_ENCRYPTION_KEY"):
        crypto.parse_key(bad)
