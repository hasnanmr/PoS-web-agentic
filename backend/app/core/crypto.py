"""Field encryption and blind indexes for personal data and stored credentials.

Rules (PRD §5.12, NFR3; glossary §10):

- Secrets that are only checked (access keys, chat sessions, tablet tokens, pairing codes,
  idempotency keys) are stored as SHA-256 hashes, never readable back (`sha256_hex`).
- Values that must be shown again are encrypted with AES-256-GCM: customer name, phone, and
  delivery address, booking guest name and phone, the table QR token (O8 re-download), and
  the booking code (C12). Stored as text `enc:v1:<base64(nonce | ciphertext+tag)>`.
- Every ciphertext is bound to its column through the associated data (`context`, e.g.
  `customers.phone`), so a value copied into another column does not decrypt.
- Equality lookups on encrypted values (phone number for the 2-booking limit and C12 lookup,
  booking code) use a keyed blind index, HMAC-SHA256 (`blind_index`): low-entropy values
  like a phone number cannot be brute-forced from the index without the key.
- Both keys are derived (HKDF-SHA256) from one 32-byte `DATA_ENCRYPTION_KEY`. Losing it means
  the encrypted values cannot be read; rotating it needs a re-encryption run.
- Values written before encryption (plaintext, no `enc:` prefix) are still returned as they
  are; `app.cli encrypt-existing` re-writes them encrypted.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import logging
import os
from dataclasses import dataclass

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

logger = logging.getLogger(__name__)

PREFIX = "enc:v1:"
NONCE_BYTES = 12
# Local development only: a fixed, public key so `APP_ENV=local` works without setup. Never
# accepted outside local (see `Settings`).
DEV_KEY = base64.b64encode(b"thinker-local-dev-key-not-secret").decode()


class CryptoError(RuntimeError):
    """A value could not be decrypted (wrong key, wrong column, or tampered)."""


@dataclass(frozen=True, slots=True)
class _Keys:
    aead: AESGCM
    index_key: bytes


_keys: _Keys | None = None


def parse_key(value: str) -> bytes:
    """`DATA_ENCRYPTION_KEY` is 32 random bytes, base64 (e.g. `openssl rand -base64 32`)."""
    try:
        raw = base64.b64decode(value.strip(), validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("DATA_ENCRYPTION_KEY must be base64") from exc
    if len(raw) != 32:
        raise ValueError("DATA_ENCRYPTION_KEY must be 32 bytes (openssl rand -base64 32)")
    return raw


def _derive(master: bytes, info: bytes) -> bytes:
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=info).derive(master)


def configure(key: str | None) -> None:
    """Called once at startup with `DATA_ENCRYPTION_KEY` (None = the local dev key)."""
    global _keys
    if key is None:
        logger.warning("DATA_ENCRYPTION_KEY not set: using the public local dev key")
        key = DEV_KEY
    master = parse_key(key)
    _keys = _Keys(
        aead=AESGCM(_derive(master, b"thinker field encryption v1")),
        index_key=_derive(master, b"thinker blind index v1"),
    )


def _k() -> _Keys:
    if _keys is None:
        configure(None)  # tests and scripts that never built the app: local dev key
    assert _keys is not None  # noqa: S101
    return _keys


def encrypt(value: str | None, context: str) -> str | None:
    if value is None:
        return None
    nonce = os.urandom(NONCE_BYTES)
    sealed = _k().aead.encrypt(nonce, value.encode(), context.encode())
    return PREFIX + base64.urlsafe_b64encode(nonce + sealed).decode()


def decrypt(value: str | None, context: str) -> str | None:
    """The plaintext; a legacy plaintext value (no prefix) is returned unchanged."""
    if value is None or not value.startswith(PREFIX):
        return value
    try:
        blob = base64.urlsafe_b64decode(value[len(PREFIX) :])
        return _k().aead.decrypt(blob[:NONCE_BYTES], blob[NONCE_BYTES:], context.encode()).decode()
    except (InvalidTag, ValueError, binascii.Error) as exc:
        raise CryptoError(f"cannot decrypt {context}") from exc


def is_encrypted(value: str | None) -> bool:
    return value is not None and value.startswith(PREFIX)


def blind_index(value: str, context: str) -> str:
    """HMAC-SHA256 of a normalized value, per context (hex, 64 characters)."""
    msg = context.encode() + b"\x00" + value.encode()
    return hmac.new(_k().index_key, msg, hashlib.sha256).hexdigest()


def sha256_hex(value: str) -> str:
    """Plain SHA-256 for high-entropy secrets (random tokens and keys)."""
    return hashlib.sha256(value.encode()).hexdigest()
