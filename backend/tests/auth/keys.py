"""Test helpers: an EC signing key, its JWKS, and a token factory."""

from __future__ import annotations

import json
import time
from typing import Any

import jwt
from cryptography.hazmat.primitives.asymmetric import ec
from jwt.algorithms import ECAlgorithm

from app.auth.tokens import JwksCache, TokenVerifier

ISSUER = "https://test.supabase.co/auth/v1"
AUDIENCE = "authenticated"
KID = "test-key-1"

PRIVATE_KEY = ec.generate_private_key(ec.SECP256R1())
OTHER_KEY = ec.generate_private_key(ec.SECP256R1())


def jwks() -> dict[str, Any]:
    jwk = json.loads(ECAlgorithm.to_jwk(PRIVATE_KEY.public_key()))
    jwk.update({"kid": KID, "alg": "ES256", "use": "sig"})
    return {"keys": [jwk]}


def make_verifier(fetch_counter: list[int] | None = None) -> TokenVerifier:
    def fetch() -> dict[str, Any]:
        if fetch_counter is not None:
            fetch_counter.append(1)
        return jwks()

    return TokenVerifier(
        JwksCache(fetch, ttl_seconds=600, min_refresh_seconds=30),
        issuer=ISSUER,
        audience=AUDIENCE,
        algorithms=["ES256", "RS256"],
    )


def make_token(
    *,
    sub: str = "00000000-0000-0000-0000-0000000000f1",
    tenant_id: str | None = "00000000-0000-0000-0000-00000000000a",
    app_role: str | None = "staff",
    exp_in: int = 900,
    iss: str = ISSUER,
    aud: str = AUDIENCE,
    kid: str = KID,
    key: Any = PRIVATE_KEY,
    alg: str = "ES256",
) -> str:
    now = int(time.time())
    claims: dict[str, Any] = {
        "sub": sub,
        "iss": iss,
        "aud": aud,
        "iat": now,
        "exp": now + exp_in,
        "role": "authenticated",
        "email": "rina@kopisenja.id",
    }
    if tenant_id is not None:
        claims["tenant_id"] = tenant_id
    if app_role is not None:
        claims["app_role"] = app_role
    return jwt.encode(claims, key, algorithm=alg, headers={"kid": kid})
