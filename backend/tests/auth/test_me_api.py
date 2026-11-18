from __future__ import annotations

from uuid import UUID

from fastapi.testclient import TestClient

from app.auth.principal import AuthError, Principal
from app.auth.tokens import VerifiedToken
from app.config import Settings
from app.main import create_app

from .keys import make_token, make_verifier


class FakeDirectory:
    def __init__(self, principal: Principal | None = None, error: AuthError | None = None) -> None:
        self.principal = principal
        self.error = error

    async def resolve(self, token: VerifiedToken) -> Principal:
        if self.error:
            raise self.error
        assert self.principal is not None
        return self.principal


def client(directory: FakeDirectory) -> TestClient:
    app = create_app(Settings(), token_verifier=make_verifier(), user_directory=directory)
    return TestClient(app)


def test_missing_token_is_401_with_error_shape() -> None:
    res = client(FakeDirectory()).get("/api/v1/me")
    assert res.status_code == 401
    assert res.json()["error"]["code"] == "unauthenticated"
    assert res.headers["www-authenticate"] == "Bearer"


def test_hs256_token_is_401() -> None:
    token = make_token(key="legacy-shared-secret-from-old-project-0123456789", alg="HS256")
    res = client(FakeDirectory()).get("/api/v1/me", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 401
    assert res.json()["error"]["code"] == "algorithm_not_allowed"


def test_deactivated_user_is_403_even_with_valid_token() -> None:
    directory = FakeDirectory(error=AuthError(403, "account_inactive", "account is deactivated"))
    res = client(directory).get("/api/v1/me", headers={"Authorization": f"Bearer {make_token()}"})
    assert res.status_code == 403
    assert res.json()["error"]["code"] == "account_inactive"


def test_invited_owner_gets_onboarding_required() -> None:
    principal = Principal(
        UUID("00000000-0000-0000-0000-0000000000e0"), "owner_pending", None, "new@cafe.id", None
    )
    token = make_token(app_role="owner_pending", tenant_id=None)
    res = client(FakeDirectory(principal)).get(
        "/api/v1/me", headers={"Authorization": f"Bearer {token}"}
    )
    assert res.status_code == 200
    body = res.json()
    assert body["role"] == "owner_pending"
    assert body["onboarding_required"] is True
    assert body["tenant"] is None
    assert body["outlets"] == []


def test_auth_not_configured_is_503() -> None:
    app = create_app(Settings())  # no JWKS settings in local
    res = TestClient(app).get("/api/v1/me", headers={"Authorization": "Bearer x"})
    assert res.status_code == 503
    assert res.json()["error"]["code"] == "auth_not_configured"
