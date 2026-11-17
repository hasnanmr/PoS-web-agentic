"""Supabase access-token verification (T-006, Appendix B.3).

- Public keys come from the project's JWKS endpoint and are cached; an unknown
  `kid` triggers at most one refresh per `min_refresh_seconds`.
- Only asymmetric algorithms from settings are accepted. HS256 (shared secret)
  and `none` are always rejected, even if a key with that `kid` existed.
- Checks: signature, `iss`, `aud`, `exp`, `sub`, and the claim contract from
  T-113: `app_role` in {owner, staff, owner_pending}; `tenant_id` required unless
  `app_role` is `owner_pending`.
- The token only identifies the caller. Authorization uses the live database
  row (see `app.auth.deps`).
"""

from __future__ import annotations

import json
import threading
import time
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal
from uuid import UUID

import jwt
from jwt import PyJWK, PyJWKSet

AppRole = Literal["owner", "staff", "owner_pending"]
_APP_ROLES: frozenset[str] = frozenset({"owner", "staff", "owner_pending"})
_SYMMETRIC_OR_NONE = frozenset({"HS256", "HS384", "HS512", "NONE"})


class TokenError(Exception):
    """The token is missing, malformed, expired, or fails verification."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class VerifiedToken:
    user_id: UUID
    app_role: AppRole
    tenant_id: UUID | None
    email: str | None
    expires_at: int
    claims: dict[str, Any]


JwksFetcher = Callable[[], dict[str, Any]]


def http_jwks_fetcher(url: str, timeout: float = 5.0) -> JwksFetcher:
    def fetch() -> dict[str, Any]:
        if not url.startswith("https://") and not url.startswith("http://localhost"):
            raise TokenError("jwks_unavailable", "JWKS URL must use https")
        req = urllib.request.Request(url, headers={"Accept": "application/json"})  # noqa: S310
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 - scheme checked
            return json.loads(resp.read())

    return fetch


class JwksCache:
    """Thread-safe JWKS cache with TTL and rate-limited refresh on unknown kid."""

    def __init__(
        self,
        fetcher: JwksFetcher,
        *,
        ttl_seconds: float = 600,
        min_refresh_seconds: float = 30,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._fetcher = fetcher
        self._ttl = ttl_seconds
        self._min_refresh = min_refresh_seconds
        self._clock = clock
        self._keys: dict[str, PyJWK] = {}
        self._fetched_at: float | None = None
        self._lock = threading.Lock()

    def _refresh(self) -> None:
        data = self._fetcher()
        keyset = PyJWKSet.from_dict(data)
        self._keys = {k.key_id: k for k in keyset.keys if k.key_id}
        self._fetched_at = self._clock()

    def get(self, kid: str) -> PyJWK:
        with self._lock:
            now = self._clock()
            stale = self._fetched_at is None or now - self._fetched_at > self._ttl
            if stale:
                self._refresh()
            elif kid not in self._keys and now - (self._fetched_at or 0) >= self._min_refresh:
                self._refresh()
            key = self._keys.get(kid)
        if key is None:
            raise TokenError("unknown_key", "token signed with an unknown key")
        return key


class TokenVerifier:
    def __init__(
        self,
        jwks: JwksCache,
        *,
        issuer: str,
        audience: str,
        algorithms: list[str],
        leeway_seconds: int = 10,
    ) -> None:
        bad = [a for a in algorithms if a.upper() in _SYMMETRIC_OR_NONE]
        if bad:
            raise ValueError(f"symmetric or none algorithms are not allowed: {bad}")
        self._jwks = jwks
        self._issuer = issuer
        self._audience = audience
        self._algorithms = algorithms
        self._leeway = leeway_seconds

    def verify(self, token: str) -> VerifiedToken:
        try:
            header = jwt.get_unverified_header(token)
        except jwt.PyJWTError as exc:
            raise TokenError("malformed", "malformed token") from exc

        alg = str(header.get("alg", "")).upper()
        if alg in _SYMMETRIC_OR_NONE or header.get("alg") not in self._algorithms:
            raise TokenError(
                "algorithm_not_allowed", f"algorithm {header.get('alg')!r} not allowed"
            )
        kid = header.get("kid")
        if not kid:
            raise TokenError("unknown_key", "token has no key id")

        key = self._jwks.get(str(kid))
        try:
            claims: dict[str, Any] = jwt.decode(
                token,
                key=key,
                algorithms=self._algorithms,
                audience=self._audience,
                issuer=self._issuer,
                leeway=self._leeway,
                options={"require": ["exp", "sub", "iss", "aud"]},
            )
        except jwt.ExpiredSignatureError as exc:
            raise TokenError("expired", "token expired") from exc
        except jwt.InvalidAudienceError as exc:
            raise TokenError("invalid_audience", "wrong audience") from exc
        except jwt.InvalidIssuerError as exc:
            raise TokenError("invalid_issuer", "wrong issuer") from exc
        except jwt.PyJWTError as exc:
            raise TokenError("invalid_token", "token verification failed") from exc

        return _claims_to_token(claims)


def _claims_to_token(claims: dict[str, Any]) -> VerifiedToken:
    role = claims.get("app_role")
    if role not in _APP_ROLES:
        raise TokenError("missing_claims", "token has no valid app_role claim")
    try:
        user_id = UUID(str(claims["sub"]))
    except (KeyError, ValueError) as exc:
        raise TokenError("invalid_token", "sub is not a user id") from exc

    tenant_raw = claims.get("tenant_id")
    if role == "owner_pending":
        tenant_id = None
    else:
        if not tenant_raw:
            raise TokenError("missing_claims", "token has no tenant_id claim")
        try:
            tenant_id = UUID(str(tenant_raw))
        except ValueError as exc:
            raise TokenError("missing_claims", "tenant_id is not a uuid") from exc

    return VerifiedToken(
        user_id=user_id,
        app_role=role,
        tenant_id=tenant_id,
        email=claims.get("email"),
        expires_at=int(claims["exp"]),
        claims=claims,
    )
