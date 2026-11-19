"""Signed URLs for menu photos (T-132), shared by O5 (owner) and S1/M2 (counter menu).

Rows from core carry `photo_path`; the API replaces it with `photo_url`, a short-lived
signed URL from the private bucket. Without Storage configured, or if signing fails, the
URL is null and the screen shows the empty photo box.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import Request

from app.storage import ObjectStorage, StorageError

logger = logging.getLogger(__name__)


def storage(request: Request) -> ObjectStorage | None:
    return getattr(request.app.state, "storage", None)


async def attach_photo_urls(request: Request, rows: list[dict[str, Any]]) -> None:
    settings = request.app.state.settings
    paths = sorted({r["photo_path"] for r in rows if r.get("photo_path")})
    urls: dict[str, str] = {}
    store = storage(request)
    if store is not None and paths:
        try:
            urls = await asyncio.to_thread(
                store.signed_urls, settings.menu_photo_bucket, paths, settings.signed_url_seconds
            )
        except StorageError as exc:
            logger.warning("menu photo signing failed: %s", exc)
    for r in rows:
        path = r.pop("photo_path", None)
        r["photo_url"] = urls.get(path) if path else None
