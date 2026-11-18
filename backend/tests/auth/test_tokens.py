from __future__ import annotations

import base64
import json
from uuid import UUID

import jwt
import pytest

from app.auth.tokens import TokenError, TokenVerifier

from .keys import OTHER_KEY, make_token, make_verifier


def test_valid_es256_token_is_accepted() -> None:
    verified = make_verifier().verify(make_token())
    assert verified.user_id == UUID("00000000-0000-0000-0000-0000000000f1")
    assert verified.tenant_id == UUID("00000000-0000-0000-0000-00000000000a")
    assert verified.app_role == "staff"


def test_owner_pending_has_no_tenant() -> None:
    verified = make_verifier().verify(make_token(app_role="owner_pending", tenant_id=None))
    assert verified.app_role == "owner_pending"
    assert verified.tenant_id is None


@pytest.mark.parametrize(
    ("kwargs", "code"),
    [
        ({"exp_in": -60}, "expired"),
        ({"iss": "https://evil.example/auth/v1"}, "invalid_issuer"),
        ({"aud": "anon"}, "invalid_audience"),
        ({"kid": "unknown-kid"}, "unknown_key"),
        ({"key": OTHER_KEY}, "invalid_token"),
        ({"app_role": None}, "missing_claims"),
        ({"app_role": "admin"}, "missing_claims"),
        ({"tenant_id": None}, "missing_claims"),
    ],
)
def test_rejected_tokens(kwargs: dict, code: str) -> None:
    with pytest.raises(TokenError) as exc:
        make_verifier().verify(make_token(**kwargs))
    assert exc.value.code == code


def test_hs256_token_is_rejected_even_with_known_kid() -> None:
    token = make_token(key="legacy-shared-secret-from-old-project-0123456789", alg="HS256")
    with pytest.raises(TokenError) as exc:
        make_verifier().verify(token)
    assert exc.value.code == "algorithm_not_allowed"


def test_alg_none_is_rejected() -> None:
    def b64(obj: dict) -> str:
        return base64.urlsafe_b64encode(json.dumps(obj).encode()).rstrip(b"=").decode()

    unsigned = f"{b64({'alg': 'none', 'kid': 'test-key-1'})}.{b64({'sub': 'x'})}."
    with pytest.raises(TokenError) as exc:
        make_verifier().verify(unsigned)
    assert exc.value.code == "algorithm_not_allowed"


def test_garbage_is_malformed() -> None:
    with pytest.raises(TokenError) as exc:
        make_verifier().verify("not-a-jwt")
    assert exc.value.code == "malformed"


def test_unknown_kid_refresh_is_rate_limited() -> None:
    fetches: list[int] = []
    verifier = make_verifier(fetches)
    verifier.verify(make_token())
    for _ in range(5):
        with pytest.raises(TokenError):
            verifier.verify(make_token(kid="rotated-key"))
    assert len(fetches) == 1  # no refetch storm within min_refresh_seconds


def test_verifier_refuses_symmetric_configuration() -> None:
    with pytest.raises(ValueError, match="not allowed"):
        TokenVerifier(make_verifier()._jwks, issuer="x", audience="y", algorithms=["HS256"])


def test_pyjwt_rejects_tampered_payload() -> None:
    token = make_token()
    header, _payload, sig = token.split(".")
    claims = jwt.decode(token, options={"verify_signature": False})
    claims["tenant_id"] = "00000000-0000-0000-0000-00000000000b"
    forged = base64.urlsafe_b64encode(json.dumps(claims).encode()).rstrip(b"=").decode()
    with pytest.raises(TokenError):
        make_verifier().verify(f"{header}.{forged}.{sig}")
