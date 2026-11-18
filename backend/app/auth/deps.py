"""FastAPI dependencies for authentication and role checks (T-006, T-013 groundwork)."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from app.api.errors import ApiError
from app.auth.principal import AuthError, Principal, UserDirectory
from app.auth.tokens import TokenError, TokenVerifier

_WWW = {"WWW-Authenticate": "Bearer"}


def _verifier(request: Request) -> TokenVerifier:
    verifier: TokenVerifier | None = getattr(request.app.state, "token_verifier", None)
    if verifier is None:
        raise ApiError(503, "auth_not_configured", "authentication is not configured")
    return verifier


def _directory(request: Request) -> UserDirectory:
    directory: UserDirectory | None = getattr(request.app.state, "user_directory", None)
    if directory is None:
        raise ApiError(503, "database_not_configured", "database is not configured")
    return directory


def _bearer(request: Request) -> str:
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise ApiError(401, "unauthenticated", "missing bearer token", headers=_WWW)
    return token.strip()


async def current_principal(request: Request) -> Principal:
    token = _bearer(request)
    try:
        verified = _verifier(request).verify(token)
    except TokenError as exc:
        raise ApiError(401, exc.code, str(exc), headers=_WWW) from None
    try:
        principal = await _directory(request).resolve(verified)
    except AuthError as exc:
        raise ApiError(exc.status_code, exc.code, str(exc)) from None
    request.state.principal = principal
    return principal


async def tenant_user(principal: Annotated[Principal, Depends(current_principal)]) -> Principal:
    """Owner or staff of an existing tenant (not an owner still onboarding)."""
    if principal.onboarding_required:
        raise ApiError(403, "onboarding_required", "create the business first")
    return principal


async def owner_only(principal: Annotated[Principal, Depends(tenant_user)]) -> Principal:
    """Owner-only endpoints (`/api/v1/owner/*`). Role is read live, not from the claim."""
    if not principal.is_owner:
        raise ApiError(403, "forbidden", "owner only")
    return principal


async def pending_owner(principal: Annotated[Principal, Depends(current_principal)]) -> Principal:
    """Invited owner who has not created the business yet (O1 onboarding)."""
    if not principal.onboarding_required:
        raise ApiError(409, "already_onboarded", "this account already has a business")
    return principal


CurrentPrincipal = Annotated[Principal, Depends(current_principal)]
TenantUser = Annotated[Principal, Depends(tenant_user)]
OwnerOnly = Annotated[Principal, Depends(owner_only)]
PendingOwner = Annotated[Principal, Depends(pending_owner)]
