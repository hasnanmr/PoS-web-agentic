"""Minimal client for the Supabase Auth (GoTrue) admin API (T-006).

Uses the service role key, which is ONLY for auth administration (inviting owners
and staff, banning deactivated accounts) and never for tenant data (Appendix B.4).

Endpoints used (verify against the current Supabase Auth API docs before the
first deploy; they could not be checked from the authoring environment):
- POST {SUPABASE_URL}/auth/v1/invite                 body {"email", "data"} → user
- PUT  {SUPABASE_URL}/auth/v1/admin/users/{user_id}  body {"ban_duration": "..."}
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any
from uuid import UUID

# Effectively permanent; reactivation sets "none".
PERMANENT_BAN = "876000h"


class SupabaseAdminError(RuntimeError):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(f"Supabase Auth admin API error {status}: {message}")
        self.status = status


@dataclass(frozen=True, slots=True)
class InvitedUser:
    user_id: UUID
    email: str


class SupabaseAdmin:
    def __init__(self, supabase_url: str, service_role_key: str, timeout: float = 10.0) -> None:
        if not supabase_url.startswith("https://") and not supabase_url.startswith(
            ("http://localhost", "http://127.0.0.1")
        ):
            raise ValueError("SUPABASE_URL must use https")
        self._base = supabase_url.rstrip("/") + "/auth/v1"
        self._key = service_role_key
        self._timeout = timeout

    def _request(self, method: str, path: str, body: dict[str, Any]) -> dict[str, Any]:
        req = urllib.request.Request(  # noqa: S310 - scheme validated in __init__
            self._base + path,
            method=method,
            data=json.dumps(body).encode(),
            headers={
                "apikey": self._key,
                "Authorization": f"Bearer {self._key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:  # noqa: S310
                raw = resp.read()
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode(errors="replace")[:300]
            raise SupabaseAdminError(exc.code, detail) from None
        return json.loads(raw) if raw else {}

    def invite_user(
        self, email: str, *, data: dict[str, Any] | None = None, redirect_to: str | None = None
    ) -> InvitedUser:
        body: dict[str, Any] = {"email": email, "data": data or {}}
        path = "/invite"
        if redirect_to:
            path += "?" + urllib.parse.urlencode({"redirect_to": redirect_to})
        result = self._request("POST", path, body)
        user = result.get("user", result)
        return InvitedUser(user_id=UUID(user["id"]), email=user.get("email", email))

    def ban_user(self, user_id: UUID, duration: str = PERMANENT_BAN) -> None:
        """Block refresh/sign-in for a deactivated account (US-003)."""
        self._request("PUT", f"/admin/users/{user_id}", {"ban_duration": duration})

    def unban_user(self, user_id: UUID) -> None:
        self._request("PUT", f"/admin/users/{user_id}", {"ban_duration": "none"})
