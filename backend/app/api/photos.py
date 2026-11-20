"""Signed URLs for menu photos (T-132), shared by O5 (owner) and S1/M2 (counter menu).

Rows from core carry `photo_path`; the API replaces it with `photo_url`, a signed URL from the
private bucket. URLs are cached per object for most of their lifetime: the counter menu reloads
after every sale, and a stable URL lets the browser keep the image instead of downloading it
again (and the screen does not wait on Storage). Every URL handed out still has at least
`signed_url_min_left_seconds` to live. Without Storage, or if signing fails, the URL is null
and the screen shows the empty photo box.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from fastapi import Request

from app.storage import ObjectStorage, StorageError

logger = logging.getLogger(__name__)

_MAX_CACHED = 5000
# (bucket, path) → (url, expires_at on the monotonic clock). Per process; a photo replaced or
# deleted gets a new path, so stale entries are never served for another photo.
_cache: dict[tuple[str, str], tuple[str, float]] = {}


def storage(request: Request) -> ObjectStorage | None:
    return getattr(request.app.state, "storage", None)


def _prune(now: float, min_left: float) -> None:
    for key in [k for k, (_, exp) in _cache.items() if exp - now < min_left]:
        del _cache[key]
    while len(_cache) > _MAX_CACHED:
        del _cache[next(iter(_cache))]


async def attach_photo_urls(request: Request, rows: list[dict[str, Any]]) -> None:
    settings = request.app.state.settings
    bucket = settings.menu_photo_bucket
    store = storage(request)
    if store is None:
        for r in rows:
            r.pop("photo_path", None)
            r["photo_url"] = None
        return
    paths = sorted({r["photo_path"] for r in rows if r.get("photo_path")})
    now = time.monotonic()
    min_left = settings.signed_url_min_left_seconds
    urls: dict[str, str] = {}
    missing = []
    for p in paths:
        hit = _cache.get((bucket, p))
        if hit and hit[1] - now >= min_left:
            urls[p] = hit[0]
        else:
            missing.append(p)
    if missing:
        ttl = settings.signed_url_seconds
        try:
            fresh = await asyncio.to_thread(store.signed_urls, bucket, missing, ttl)
        except StorageError as exc:
            logger.warning("menu photo signing failed: %s", exc)
            fresh = {}
        _prune(now, min_left)
        for p, url in fresh.items():
            _cache[(bucket, p)] = (url, now + ttl)
        urls.update(fresh)
    for r in rows:
        path = r.pop("photo_path", None)
        r["photo_url"] = urls.get(path) if path else None
