"""Private Supabase Storage buckets (T-132: menu photos).

The backend uploads and signs objects with the service role key; the browser never gets
a Storage key, only short-lived signed URLs. Buckets are private (no public URLs).

Endpoints used (Supabase Storage API; verify against the current docs before changing):
- POST   {SUPABASE_URL}/storage/v1/object/{bucket}/{path}   raw body → upload
- POST   {SUPABASE_URL}/storage/v1/object/sign/{bucket}     {"expiresIn", "paths"} → signed URLs
- DELETE {SUPABASE_URL}/storage/v1/object/{bucket}          {"prefixes": [paths]} → remove
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Protocol


class StorageError(RuntimeError):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(f"Supabase Storage error {status}: {message}")
        self.status = status


class ObjectStorage(Protocol):
    """What the API needs from object storage (tests inject a fake)."""

    def upload(self, bucket: str, path: str, data: bytes, content_type: str) -> None: ...

    def signed_urls(self, bucket: str, paths: list[str], expires_in: int) -> dict[str, str]: ...

    def remove(self, bucket: str, paths: list[str]) -> None: ...


class SupabaseStorage:
    def __init__(self, supabase_url: str, service_role_key: str, timeout: float = 15.0) -> None:
        if not supabase_url.startswith("https://") and not supabase_url.startswith(
            ("http://localhost", "http://127.0.0.1")
        ):
            raise ValueError("SUPABASE_URL must use https")
        self._root = supabase_url.rstrip("/") + "/storage/v1"
        self._key = service_role_key
        self._timeout = timeout

    def _request(
        self, method: str, path: str, body: bytes, content_type: str, extra: dict[str, str]
    ) -> Any:
        req = urllib.request.Request(  # noqa: S310 - scheme validated in __init__
            self._root + path,
            method=method,
            data=body,
            headers={
                "apikey": self._key,
                "Authorization": f"Bearer {self._key}",
                "Content-Type": content_type,
                "Accept": "application/json",
                **extra,
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:  # noqa: S310
                raw = resp.read()
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode(errors="replace")[:300]
            raise StorageError(exc.code, detail) from None
        except urllib.error.URLError as exc:
            raise StorageError(0, str(exc.reason)) from None
        return json.loads(raw) if raw else None

    def _json(self, method: str, path: str, body: dict[str, Any]) -> Any:
        return self._request(method, path, json.dumps(body).encode(), "application/json", {})

    @staticmethod
    def _quote(path: str) -> str:
        return urllib.parse.quote(path, safe="/")

    def upload(self, bucket: str, path: str, data: bytes, content_type: str) -> None:
        self._request(
            "POST",
            f"/object/{bucket}/{self._quote(path)}",
            data,
            content_type,
            {"x-upsert": "false", "cache-control": "3600"},
        )

    def signed_urls(self, bucket: str, paths: list[str], expires_in: int) -> dict[str, str]:
        if not paths:
            return {}
        rows = self._json(
            "POST", f"/object/sign/{bucket}", {"expiresIn": expires_in, "paths": paths}
        )
        out: dict[str, str] = {}
        for row in rows or []:
            signed = row.get("signedURL")
            if signed and not row.get("error"):
                out[row["path"]] = self._root + signed
        return out

    def remove(self, bucket: str, paths: list[str]) -> None:
        if paths:
            self._json("DELETE", f"/object/{bucket}", {"prefixes": paths})
